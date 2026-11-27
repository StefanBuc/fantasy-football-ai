"""Persist scheduling state beside prediction history; never store credentials."""

from datetime import timedelta
import json
import os
import sqlite3

from filelock import FileLock
import pandas as pd

from app.services.prediction_history import prediction_history, utc_now
from app.services.performance import logger
from app.config.espn_config import get_local_espn_config, local_espn_api_enabled

POLL_SECONDS = 60
CAPTURE_INTERVAL = timedelta(minutes=15)
CAPTURE_WINDOW = timedelta(hours=6)
SYNC_INTERVAL = timedelta(hours=6)
RETRY_INTERVAL = timedelta(minutes=15)


def automation_enabled():
    return os.getenv("FANTASY_AUTOMATION_ENABLED", "true").strip().lower() in {"1", "true", "yes"}


def nfl_season(now):
    eastern = pd.Timestamp(now).tz_convert("America/New_York")
    return eastern.year - 1 if eastern.month <= 2 else eastern.year


def operation_lock():
    path = prediction_history.path.with_suffix(".automation.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path), timeout=0)


class AccuracyJobs:
    def connect(self):
        return prediction_history.connect()

    def prepare(self, connection):
        connection.execute("""CREATE TABLE IF NOT EXISTS accuracy_targets (
            scope TEXT NOT NULL, season INTEGER NOT NULL, mode TEXT NOT NULL,
            PRIMARY KEY(scope, season))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS accuracy_jobs (
            scope TEXT NOT NULL, season INTEGER NOT NULL, kind TEXT NOT NULL,
            week INTEGER, state TEXT NOT NULL, last_started_at TEXT,
            last_finished_at TEXT, last_success_at TEXT, last_error TEXT,
            next_run_at TEXT, result TEXT,
            PRIMARY KEY(scope, season, kind))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS accuracy_worker (
            id INTEGER PRIMARY KEY CHECK(id=1), last_checked_at TEXT, last_error TEXT)""")

    def register(self, league_id, season, mode):
        with self.connect() as connection:
            self.prepare(connection)
            connection.execute("""INSERT INTO accuracy_targets VALUES (?,?,?)
                ON CONFLICT(scope,season) DO UPDATE SET mode=excluded.mode
                WHERE accuracy_targets.mode != excluded.mode""", (f"espn:{league_id}", season, mode))

    def targets(self):
        with self.connect() as connection:
            self.prepare(connection)
            return [dict(row) for row in connection.execute("SELECT * FROM accuracy_targets ORDER BY season,scope")]

    def heartbeat(self, now, error=None):
        with self.connect() as connection:
            self.prepare(connection)
            connection.execute("""INSERT INTO accuracy_worker VALUES (1,?,?)
                ON CONFLICT(id) DO UPDATE SET last_checked_at=excluded.last_checked_at,
                last_error=excluded.last_error""", (now.isoformat(), error))

    def recover_interrupted(self, now):
        # Holding operation_lock proves no live scheduler/manual sync owns these rows.
        with self.connect() as connection:
            self.prepare(connection)
            connection.execute("""UPDATE accuracy_jobs SET state='error',last_finished_at=?,
                last_error=CASE WHEN kind='capture' THEN
                    'Capture was interrupted; it will retry if a game is still upcoming.' ELSE
                    'Results sync was interrupted; it will retry when eligible.' END,
                next_run_at=? WHERE state='running'""", (now.isoformat(), now.isoformat()))

    def job(self, season, scope, kind):
        with self.connect() as connection:
            self.prepare(connection)
            row = connection.execute("SELECT * FROM accuracy_jobs WHERE season=? AND scope=? AND kind=?",
                                     (season, scope, kind)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["result"] = json.loads(item["result"]) if item["result"] else None
        return item

    def due(self, season, scope, kind, now, week=None):
        item = self.job(season, scope, kind)
        # The caller holds the process-shared operation lock. A leftover running
        # row therefore belongs to a stopped process, and can be retried now.
        return (item is None or item["state"] == "running" or item["week"] != week
                or item["next_run_at"] is None or item["next_run_at"] <= now.isoformat())

    def begin(self, season, scope, kind, now, week=None):
        with self.connect() as connection:
            self.prepare(connection)
            connection.execute("""INSERT INTO accuracy_jobs
                (scope,season,kind,week,state,last_started_at) VALUES (?,?,?,?,'running',?)
                ON CONFLICT(scope,season,kind) DO UPDATE SET week=excluded.week,
                state='running',last_started_at=excluded.last_started_at,last_error=NULL""",
                (scope, season, kind, week, now.isoformat()))

    def finish(self, season, scope, kind, now, *, result=None, error=None):
        interval = RETRY_INTERVAL if error else CAPTURE_INTERVAL if kind == "capture" else SYNC_INTERVAL
        with self.connect() as connection:
            self.prepare(connection)
            connection.execute("""UPDATE accuracy_jobs SET state=?,last_finished_at=?,
                last_success_at=CASE WHEN ? IS NULL THEN ? ELSE last_success_at END,
                last_error=?,next_run_at=?,result=? WHERE scope=? AND season=? AND kind=?""",
                ("error" if error else "success", now.isoformat(), error, now.isoformat(), error,
                 (now + interval).isoformat(), json.dumps(result) if result is not None else None,
                 scope, season, kind))

    def recent_groups(self, now):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("""SELECT scope,season,MIN(kickoff) AS kickoff
                FROM predictions WHERE kickoff >= ? AND kickoff <= ? GROUP BY scope,season""",
                ((now - timedelta(days=14)).isoformat(), (now - timedelta(hours=12)).isoformat()))]

    def status(self, season, scope):
        with self.connect() as connection:
            self.prepare(connection)
            worker = connection.execute("SELECT * FROM accuracy_worker WHERE id=1").fetchone()
            target = connection.execute("SELECT mode FROM accuracy_targets WHERE season=? AND scope=?",
                                        (season, scope)).fetchone()
        registered = scope == "weekly" or target is not None
        capture_enabled = automation_enabled() and registered and season == nfl_season(utc_now())
        note = "Captures run while the backend is running; missed games cannot be backfilled."
        if not automation_enabled():
            note = "Automatic tracking is disabled in the backend configuration."
        elif not registered:
            note = "Reconnect this league once to enable automatic captures."
        elif season != nfl_season(utc_now()):
            note = "Automatic captures follow the active NFL season. Older history can still be synced manually."
        elif target is not None and target["mode"] == "saved":
            from app.services.account_store import accounts
            connection = next((row for row in accounts.connections() if scope == f"espn:{row['league_id']}" and row["season"] == season and row["mode"] == "private"), None)
            if connection is None or connection["status"] != "connected":
                capture_enabled = False
                note = "Update the saved private-league connection to restore captures."
        elif target is not None and target["mode"] == "local":
            try:
                config = get_local_espn_config() if local_espn_api_enabled() else None
            except RuntimeError:
                config = None
            if config is None or config.season != season or scope != f"espn:{config.league_id}":
                capture_enabled = False
                note = "Private-league captures need the matching local ESPN configuration enabled."
        return {"enabled": automation_enabled(), "registered": registered,
                "capture_enabled": capture_enabled, "note": note,
                "last_checked_at": worker["last_checked_at"] if worker else None,
                "worker_error": worker["last_error"] if worker else None,
                "capture": self.job(season, scope, "capture"), "sync": self.job(season, scope, "sync"),
                "poll_seconds": POLL_SECONDS, "capture_interval_minutes": 15,
                "capture_window_hours": 6, "sync_interval_hours": 6}


accuracy_jobs = AccuracyJobs()


def register_league_tracking(league_id, season, mode):
    try:
        accuracy_jobs.register(league_id, season, mode)
    except (OSError, sqlite3.Error):
        logger.warning("Cannot register league for automatic accuracy tracking")


def run_tracked_sync(season, scope, operation):
    """Shared by the manual route and scheduler, while holding operation_lock."""
    accuracy_jobs.begin(season, scope, "sync", utc_now())
    try:
        result = operation()
    except Exception:
        accuracy_jobs.finish(season, scope, "sync", utc_now(), error="Results sync failed; retrying in 15 minutes.")
        raise
    accuracy_jobs.finish(season, scope, "sync", utc_now(), result=result)
    return result
