"""Durable weekly retraining schedule, run in its own resource-limited process."""

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
import os
import signal
from threading import Event, current_thread, main_thread
from time import monotonic
from uuid import uuid4

# Load PyTorch before pandas-backed providers on native Windows.
import torch
from filelock import FileLock, Timeout
import nfl_data_py as nfl
import pytz

from app.services.accuracy_jobs import nfl_season
from app.services.model_registry import runs_directory, atomic_json, manifest
from app.services.prediction_history import game_times
from app.services.retraining import latest_complete_week, chronological_plan, training_frames, train_position, stats_ready
from app.services.performance import logger

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")


@contextmanager
def training_time_limit(seconds):
    # Linux Docker can interrupt a blocked data download too. Native Windows
    # still checks the deadline between data stages and every training batch.
    supported = hasattr(signal, "SIGALRM") and current_thread() is main_thread()
    if supported:
        previous = signal.getsignal(signal.SIGALRM)
        def expired(*_):
            raise TimeoutError("Training job exceeded its time limit")
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        if supported:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


def training_enabled():
    return os.getenv("FANTASY_RETRAIN_ENABLED", "true").lower() in {"1", "true", "yes"}


def schedule_slot(now):
    timezone_name = os.getenv("FANTASY_TRAINING_TIMEZONE", "America/Toronto")
    zone = pytz.timezone(timezone_name)
    weekday = int(os.getenv("FANTASY_TRAINING_WEEKDAY", "1"))
    hour = int(os.getenv("FANTASY_TRAINING_HOUR", "5"))
    if weekday not in range(7) or hour not in range(24):
        raise ValueError("Invalid training weekday or hour")
    local = now.astimezone(zone)
    day = local.date() - timedelta(days=(local.weekday() - weekday) % 7)
    slot = zone.localize(datetime.combine(day, datetime.min.time()).replace(hour=hour))
    if slot > local:
        day -= timedelta(days=7)
        slot = zone.localize(datetime.combine(day, datetime.min.time()).replace(hour=hour))
    next_slot = zone.localize(datetime.combine(day + timedelta(days=7), datetime.min.time()).replace(hour=hour))
    return slot.astimezone(timezone.utc), next_slot.astimezone(timezone.utc)


def week_still_settling(schedule, season, completed, now):
    if schedule is None or not {"season", "week", "game_type"}.issubset(schedule.columns):
        return False
    regular = schedule[(schedule.season == season) & (schedule.game_type == "REG")]
    for week in regular.week.dropna().unique():
        if not completed < int(week) <= 18:
            continue
        games = regular[regular.week == week]
        times = game_times(schedule, season, int(week))
        if len(times) == 2 * len(games) and all(kickoff <= now for _, kickoff, _ in times.values()):
            return True
    return False


def read_status():
    path = runs_directory() / "status.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"state": "waiting", "positions": {}}


def training_status():
    state = read_status()
    _, next_slot = schedule_slot(datetime.now(timezone.utc))
    return {**state, "enabled": training_enabled(), "next_scheduled_at": next_slot.isoformat(),
            "timezone": os.getenv("FANTASY_TRAINING_TIMEZONE", "America/Toronto"),
            "device": os.getenv("FANTASY_TRAINING_DEVICE", "cpu"),
            "active_models": {position: {"sha256": entry["checkpoint_sha256"], "evaluation": entry["evaluation"]}
                              for position, entry in manifest()["positions"].items()}}


class RetrainingWorker:
    def __init__(self, clock=lambda: datetime.now(timezone.utc)):
        self.clock = clock
        self.stopped = Event()

    def write(self, state):
        atomic_json(runs_directory() / "status.json", state)

    def run_once(self, force=False):
        if self.stopped.is_set() or not training_enabled():
            return
        root = runs_directory()
        root.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(root / "worker.lock"), timeout=0):
                with training_time_limit(max(60, min(21600, int(os.getenv("FANTASY_TRAINING_TIMEOUT_SECONDS", "5400"))))):
                    self._run_locked(force)
        except Timeout:
            return

    def _run_locked(self, force):
        root = runs_directory()
        now = self.clock()
        slot, _ = schedule_slot(now)
        state = read_status()
        state["worker_checked_at"] = now.isoformat()
        if state.get("state") == "running":
            state.update(state="error", last_error="Training was interrupted; current models are preserved.",
                         retry_at=(now + timedelta(hours=1)).isoformat())
        self.write(state)
        if not force and ((state.get("state") != "error" and (state.get("last_scheduled_at") or "") >= slot.isoformat())
                          or (state.get("retry_at") or "") > now.isoformat()):
            return
        try:
            season = nfl_season(now)
            schedule = nfl.import_schedules([season])
            week = latest_complete_week(schedule, season, now)
            if not force and week_still_settling(schedule, season, week, now):
                state.update(state="waiting", note="Waiting for the latest week's games and published results to settle.",
                             retry_at=(now + timedelta(hours=1)).isoformat())
                self.write(state)
                return
            plan = chronological_plan(week)
            if plan is None:
                state.update(state="skipped", note="Waiting for at least 11 fully completed regular-season weeks.",
                             last_scheduled_at=slot.isoformat())
                self.write(state)
                return
            near_game = any(kickoff - timedelta(hours=6) <= now <= kickoff + timedelta(hours=8)
                            for game_week in range(1, 19)
                            for _, kickoff, _ in game_times(schedule, season, game_week).values())
            if near_game and not force:
                state.update(note="Training delayed until outside the game window.", retry_at=(now + timedelta(hours=1)).isoformat())
                self.write(state)
                return
            data_key = f"{season}:{week}"
            if not force and state.get("completed_data_key") == data_key:
                state.update(last_scheduled_at=slot.isoformat(), note="No newly completed week to train on.")
                self.write(state)
                return
            results = state.get("positions", {}) if state.get("data_key") == data_key and not force else {}
            state.update(state="running", started_at=now.isoformat(), finished_at=None, data_key=data_key,
                         last_error=None, note=None, retry_at=None, positions=results, plan=plan)
            self.write(state)
            deadline = monotonic() + max(60, min(21600, int(os.getenv("FANTASY_TRAINING_TIMEOUT_SECONDS", "5400"))))
            heartbeat = monotonic()

            def check():
                nonlocal heartbeat
                if self.stopped.is_set():
                    raise InterruptedError("Training stopped")
                if monotonic() >= deadline:
                    raise TimeoutError("Training timed out")
                if monotonic() - heartbeat >= 60:
                    state["worker_checked_at"] = self.clock().isoformat()
                    self.write(state)
                    heartbeat = monotonic()

            torch.set_num_threads(max(1, min(16, int(os.getenv("FANTASY_TRAINING_THREADS", "2")))))
            run = root / "runs" / (now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
            frames = training_frames(season, check_cancelled=check)
            if not stats_ready(frames, schedule, season, week):
                state.update(state="waiting", current_position=None,
                             note="Waiting for published player and team statistics for every game in the latest week.",
                             retry_at=(self.clock() + timedelta(hours=1)).isoformat())
                self.write(state)
                return
            for position in POSITIONS:
                check()
                if position in results and "error" not in results[position]:
                    continue
                state["current_position"] = position
                self.write(state)
                try:
                    results[position] = train_position(position, frames, season, plan, run / position, check_cancelled=check)
                except (InterruptedError, TimeoutError):
                    raise
                except Exception as error:
                    logger.warning("Retraining position=%s failed type=%s", position, type(error).__name__)
                    results[position] = {"promote": False, "error": f"Training failed ({type(error).__name__}); current model retained."}
                state["positions"] = results
                self.write(state)
            failed = any("error" in result for result in results.values())
            state.update(state="error" if failed else "complete", current_position=None,
                         finished_at=self.clock().isoformat(), retry_at=(self.clock() + timedelta(hours=1)).isoformat() if failed else None)
            if not failed:
                state.update(last_scheduled_at=slot.isoformat(), completed_data_key=data_key)
            self.write(state)
        except Exception as error:
            logger.warning("Retraining failed type=%s", type(error).__name__)
            state.update(state="error", current_position=None, finished_at=self.clock().isoformat(),
                         last_error=f"Retraining failed ({type(error).__name__}); current models retained.",
                         retry_at=(self.clock() + timedelta(hours=1)).isoformat())
            self.write(state)

    def loop(self):
        # SIGTERM interrupts batches; incomplete candidates are never activated.
        signal.signal(signal.SIGTERM, lambda *_: self.stopped.set())
        signal.signal(signal.SIGINT, lambda *_: self.stopped.set())
        while not self.stopped.is_set():
            self.run_once()
            self.stopped.wait(60)
