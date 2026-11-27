"""Run pregame captures and next-day reconciliation while the API is running."""

from datetime import timedelta
from threading import Event, Thread
from time import monotonic

from filelock import Timeout
import nfl_data_py as nfl

from app.config.espn_config import get_local_espn_config, local_espn_api_enabled
from app.config.security import auth_enabled
from app.services.account_store import accounts
from app.services.accuracy_jobs import (
    accuracy_jobs, automation_enabled, precompute_enabled, operation_lock, run_tracked_sync,
    CAPTURE_WINDOW, POLL_SECONDS,
    nfl_season,
)
from app.services.prediction_history import prediction_history, game_times, utc_now
from app.services.prediction_actuals import sync_actuals, next_morning
from app.services.projection_registry import projection_services
from app.services.projection_slate import build_projection_requests
from app.services.projection_types import PlayerProjectionRequest
from app.services.performance import logger, timed_stage


def capture_windows(schedule, season, now):
    """Group only games in the pregame window; started games never trigger work."""
    if schedule is None or not {"season", "week"}.issubset(schedule.columns):
        return {}
    result = {}
    for week in schedule.loc[schedule.season == season, "week"].dropna().unique():
        if not 1 <= int(week) <= 18:
            continue
        games = game_times(schedule, season, int(week))
        teams = {team for team, (_, kickoff, _) in games.items()
                 if now < kickoff <= now + CAPTURE_WINDOW}
        if teams:
            result[int(week)] = teams
    return result


def current_local_config():
    if auth_enabled() or not local_espn_api_enabled():
        return None
    try:
        return get_local_espn_config()
    except RuntimeError:
        return None


def precompute_week(schedule, season, now):
    """Warm during the regular season, starting one week before opening kickoff."""
    if schedule is None or not {"season", "week"}.issubset(schedule.columns):
        return None
    games = [(kickoff, int(week))
             for week in schedule.loc[schedule.season == season, "week"].dropna().unique()
             if 1 <= int(week) <= 18
             for _, kickoff, _ in game_times(schedule, season, int(week)).values()]
    upcoming = sorted((kickoff, week) for kickoff, week in games if now < kickoff)
    if upcoming and upcoming[0][0] <= now + timedelta(days=7):
        return upcoming[0][1]
    # Keep the last regular-season week's pages warm while its games finish.
    recent = sorted((kickoff, week) for kickoff, week in games
                    if now - timedelta(days=1) <= kickoff <= now)
    return recent[-1][1] if recent else None


def capture_weekly(service, season, week, teams, schedule):
    roster, _ = service.data.get_projection_roster(season=season, week=week)
    roster = roster[roster.team.isin(teams)].assign(season=season, week=week)
    opponents = {team: value[0] for team, value in game_times(schedule, season, week).items()}
    depth = service.data.get_week_depth_chart(season=season, week=week)
    saved = 0
    failures = []
    for position in ("QB", "RB", "WR", "TE", "K", "DST"):
        try:
            if position == "DST":
                requests = [PlayerProjectionRequest(player_id=team, player_name=f"{team} D/ST",
                            team=team, opponent_team=opponents[team], season=season, upcoming_week=week)
                            for team in sorted(teams)]
            elif position == "K":
                requests = [PlayerProjectionRequest(player_id=str(row.player_id), player_name=str(row.player_name),
                            team=row.team, opponent_team=opponents[row.team], season=season, upcoming_week=week)
                            for row in roster[roster.position == "K"].itertuples(index=False)]
            else:
                requests = build_projection_requests(roster, opponents, position, depth_chart_df=depth)
            if not requests:
                continue
            result = service.project_requests(position, requests)
            saved += prediction_history.record(
                season=season, week=week, schedule=schedule, generated_at=result.generated_at,
                model_revision=service.model_revision,
                model_hashes=getattr(service, "model_hashes", {}),
                samples=[{"player_id": item.request.player_id, "player_name": item.request.player_name,
                          "position": item.position, "team": item.request.team,
                          "opponent_team": item.request.opponent_team, "predicted_points": item.predicted_points,
                          "projection_method": item.projection_method} for item in result.projections],
            )
        except Exception as error:
            logger.warning("Automatic capture position=%s failed type=%s", position, type(error).__name__)
            failures.append(position)
    if failures:
        raise RuntimeError("Some positions could not be captured: " + ", ".join(failures))
    return {"saved_count": saved}


def capture_league(service, target, week, schedule, config):
    # Reuse the same matching, QB signals and live injury adjustments as Players.
    # Import lazily: routes also register leagues with the scheduling store.
    from app.routes.espn import project_league_players

    league_id, league = load_target_league(target, config)
    _, saved = project_league_players(
        league, league_id, target["season"], week, service=service,
        strict_history=True, history_schedule=schedule,
    )
    return {"saved_count": saved}


def load_target_league(target, config):
    from app.integrations.espn_fantasy import get_league

    league_id = int(target["scope"].split(":", 1)[1])
    if target["mode"] == "saved":
        config = accounts.config_for_league(league_id, target["season"])
        if config is None:
            raise RuntimeError("Saved private-league connection is unavailable.")
    credentials = {"espn_s2": config.espn_s2, "swid": config.swid} if target["mode"] in {"local", "saved"} else {}
    return league_id, get_league(league_id=league_id, year=target["season"], **credentials)


def precompute_league(service, target, week, schedule, config):
    from app.routes.espn import cached_league_projection, project_league_players

    league_id, league = load_target_league(target, config)
    # Match the week shown on first opening the app, including ESPN's rollover.
    current = getattr(league, "current_week", week)
    week = int(current) if isinstance(current, int) and 1 <= current <= 18 else week
    projection, _ = cached_league_projection(league, league_id, target["season"], week, service)
    pool, saved = project_league_players(
        league, league_id, target["season"], week, service=service,
        strict_history=True, history_schedule=schedule,
    )
    return {"team_count": len(projection.team_projections), "player_count": pool.player_count,
            "saved_count": saved, "week": week}


class AccuracyScheduler:
    def __init__(self, clock=utc_now):
        self.clock = clock
        self.stopped = Event()
        self.thread = None
        self.schedules = {}
        self.schedule_retry_at = None
        self.precomputed = set()

    def start(self):
        if self.thread is None and automation_enabled():
            self.thread = Thread(target=self._loop, name="accuracy-automation", daemon=True)
            self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=1)

    def _loop(self):
        # Delay network work until after startup; this wait is interrupted on shutdown.
        if self.stopped.wait(5):
            return
        while not self.stopped.is_set():
            try:
                self.run_once()
            except Exception as error:
                # Never log the raw exception: upstream ESPN errors may contain request details.
                logger.warning("Accuracy scheduler check failed type=%s", type(error).__name__)
            self.stopped.wait(POLL_SECONDS)

    def schedule(self, season, now):
        previous = self.schedules.get(season)
        if previous is not None and now - previous[0] < timedelta(minutes=30):
            return previous[1]
        schedule = nfl.import_schedules([season])
        self.schedules[season] = (now, schedule)
        return schedule

    def service(self, season):
        service = projection_services.get(season)
        if monotonic() - service.loaded_at > 6 * 3600:
            service = projection_services.get(season, refresh=True)
        return service

    def execute(self, season, scope, kind, operation, week=None):
        accuracy_jobs.begin(season, scope, kind, self.clock(), week)
        try:
            with timed_stage("automatic_job", kind=kind, season=season, week=week):
                result = operation()
        except Exception as error:
            logger.warning("Automatic accuracy job=%s failed type=%s", kind, type(error).__name__)
            accuracy_jobs.finish(season, scope, kind, self.clock(),
                                 error=f"{kind.capitalize()} failed; retrying in 15 minutes.")
        else:
            accuracy_jobs.finish(season, scope, kind, self.clock(), result=result)

    def run_once(self):
        if self.stopped.is_set() or not automation_enabled():
            return
        try:
            with operation_lock():
                self._run_once_locked()
        except Timeout:
            return  # Another worker or manual sync owns the same history database.

    def _run_once_locked(self):
        now = self.clock()
        accuracy_jobs.heartbeat(now)
        accuracy_jobs.recover_interrupted(now)
        season = nfl_season(now)
        config = current_local_config()
        if config is not None:
            accuracy_jobs.register(config.league_id, config.season, "local")
        targets = [{"scope": "weekly", "season": season, "mode": "weekly"}]
        saved_scopes = {(f"espn:{row['league_id']}", row["season"]) for row in accounts.connections()
                        if row["mode"] == "private" and row["status"] == "connected"} if auth_enabled() else set()
        targets.extend(target for target in accuracy_jobs.targets() if target["season"] == season and (
            target["mode"] == "public" or target["mode"] == "saved" and (target["scope"], target["season"]) in saved_scopes
            or config is not None and target["scope"] == f"espn:{config.league_id}"
            and target["season"] == config.season))

        windows = {}
        schedule = None
        if self.schedule_retry_at is None or now >= self.schedule_retry_at:
            try:
                schedule = self.schedule(season, now)
                windows = capture_windows(schedule, season, now)
                self.schedule_retry_at = None
            except Exception:
                self.schedule_retry_at = now + timedelta(minutes=15)
                accuracy_jobs.heartbeat(now, "NFL schedule unavailable; checking again in 15 minutes.")

        for week, teams in windows.items():
            for target in targets:
                if self.stopped.is_set():
                    return
                teams = capture_windows(schedule, season, self.clock()).get(week)
                if not teams:
                    break
                scope = target["scope"]
                if not accuracy_jobs.due(season, scope, "capture", self.clock(), week):
                    continue
                def capture(target=target):
                    service = self.service(season)
                    if target["mode"] == "weekly":
                        return capture_weekly(service, season, week, teams, schedule)
                    return capture_league(service, target, week, schedule, config)
                self.execute(season, scope, "capture", capture, week)

        for group in accuracy_jobs.recent_groups(self.clock()):
            if self.stopped.is_set():
                return
            if self.clock() < next_morning(group["kickoff"]):
                continue
            scope, group_season = group["scope"], group["season"]
            if accuracy_jobs.due(group_season, scope, "sync", self.clock()):
                # Same lock and durable status as the manual Sync results action.
                try:
                    run_tracked_sync(group_season, scope, lambda: sync_actuals(
                        prediction_history, group_season, scope, automatic=True))
                except Exception as error:
                    logger.warning("Automatic results sync failed type=%s", type(error).__name__)

        # Accuracy captures/syncs have priority. Warm the same page caches on
        # startup and every 30 minutes without waiting for a visitor to log in.
        week = precompute_week(schedule, season, self.clock())
        if precompute_enabled() and week is not None:
            for target in targets:
                if self.stopped.is_set():
                    return
                if target["mode"] == "weekly":
                    continue
                scope = target["scope"]
                key = (season, scope, week)
                job = accuracy_jobs.job(season, scope, "precompute")
                # Every API process warms its own in-memory data after restart;
                # failed attempts still honor the durable 15-minute backoff.
                startup = key not in self.precomputed and (job is None or job["state"] != "error")
                if startup or accuracy_jobs.due(season, scope, "precompute", self.clock(), week):
                    self.precomputed.add(key)
                    self.execute(season, scope, "precompute", lambda target=target: precompute_league(
                        self.service(season), target, week, schedule, config), week)
        accuracy_jobs.heartbeat(self.clock(),
            "NFL schedule unavailable; checking again in 15 minutes." if self.schedule_retry_at else None)
