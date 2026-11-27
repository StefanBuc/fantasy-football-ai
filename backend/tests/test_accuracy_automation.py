from datetime import datetime, timedelta, timezone
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pandas as pd
import pytest

import main
from app.services import accuracy_jobs as jobs_module
from app.services import accuracy_scheduler as scheduler_module
from app.services import prediction_history as history_module
from app.services import prediction_actuals as actuals_module
from app.services.accuracy_jobs import accuracy_jobs, operation_lock, nfl_season
from app.services.accuracy_scheduler import AccuracyScheduler, capture_windows, capture_weekly, capture_league
from app.services.prediction_actuals import next_morning
from app.services.prediction_history import prediction_history
from app.services.projection_types import PlayerProjection, ProjectionSlateResult

UTC = timezone.utc
PREGAME = datetime(2026, 11, 8, 17, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 8, 18, tzinfo=UTC)


def schedule(**updates):
    return pd.DataFrame([{"season": 2026, "week": 10, "game_type": "REG", "home_team": "BUF",
        "away_team": "MIA", "gameday": "2026-11-08", "gametime": "13:00",
        "home_score": None, "away_score": None, "result": None, **updates}])


@pytest.fixture
def clock(monkeypatch):
    now = [PREGAME]
    monkeypatch.setenv("FANTASY_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("FANTASY_PRECOMPUTE_ENABLED", "false")
    monkeypatch.setenv("ESPN_ENABLE_LOCAL_API", "false")
    monkeypatch.setattr(history_module, "utc_now", lambda: now[0])
    monkeypatch.setattr(jobs_module, "utc_now", lambda: now[0])
    monkeypatch.setattr(actuals_module, "utc_now", lambda: now[0])
    return now


@pytest.fixture
def engine(monkeypatch, clock):
    worker = AccuracyScheduler(clock=lambda: clock[0])
    monkeypatch.setattr(worker, "schedule", lambda *args: schedule())
    monkeypatch.setattr(worker, "service", lambda *_: SimpleNamespace())
    monkeypatch.setattr(scheduler_module, "capture_weekly", Mock(return_value={"saved_count": 4}))
    return worker


def test_nfl_season_across_new_year():
    assert nfl_season(datetime(2027, 1, 7, tzinfo=UTC)) == 2026
    assert nfl_season(datetime(2027, 2, 1, tzinfo=UTC)) == 2026
    assert nfl_season(datetime(2027, 9, 1, tzinfo=UTC)) == 2027


def test_window_is_pregame_only_and_skips_unknown_times_and_playoffs():
    assert capture_windows(schedule(), 2026, KICKOFF - timedelta(hours=6)) == {10: {"BUF", "MIA"}}
    assert capture_windows(schedule(), 2026, KICKOFF - timedelta(hours=7)) == {}
    assert capture_windows(schedule(), 2026, KICKOFF) == {}
    assert capture_windows(schedule(), 2026, KICKOFF + timedelta(hours=1)) == {}
    assert capture_windows(schedule(gametime=None), 2026, PREGAME) == {}
    assert capture_windows(schedule(game_type="WC"), 2026, PREGAME) == {}


def test_no_models_or_history_captures_outside_window(engine, clock, monkeypatch):
    clock[0] = KICKOFF - timedelta(hours=7)
    service = Mock(side_effect=AssertionError("Unexpected inference"))
    monkeypatch.setattr(engine, "service", service)
    engine.run_once()
    service.assert_not_called()
    assert accuracy_jobs.status(2026, "weekly")["last_checked_at"] == clock[0].isoformat()
    assert accuracy_jobs.job(2026, "weekly", "capture") is None


def test_capture_cadence_survives_worker_restart(engine, clock, monkeypatch):
    engine.run_once()
    assert scheduler_module.capture_weekly.call_count == 1
    restarted = AccuracyScheduler(clock=lambda: clock[0])
    monkeypatch.setattr(restarted, "schedule", engine.schedule)
    monkeypatch.setattr(restarted, "service", engine.service)
    restarted.run_once()
    assert scheduler_module.capture_weekly.call_count == 1
    clock[0] += timedelta(minutes=16)
    restarted.run_once()
    assert scheduler_module.capture_weekly.call_count == 2
    job = accuracy_jobs.job(2026, "weekly", "capture")
    assert job["last_success_at"] == clock[0].isoformat()
    assert job["result"] == {"saved_count": 4}


def test_overlapping_workers_skip_work_without_waiting(engine, monkeypatch):
    schedule_call = Mock(side_effect=AssertionError("Overlapping job"))
    monkeypatch.setattr(engine, "schedule", schedule_call)
    with operation_lock():
        engine.run_once()
    schedule_call.assert_not_called()


def test_abandoned_running_job_is_retried_after_restart(engine, clock):
    accuracy_jobs.begin(2026, "weekly", "capture", clock[0], 10)
    engine.run_once()
    assert scheduler_module.capture_weekly.call_count == 1
    assert accuracy_jobs.job(2026, "weekly", "capture")["state"] == "success"


def test_late_restart_clears_running_status_without_backfilling(engine, clock):
    accuracy_jobs.begin(2026, "weekly", "capture", clock[0], 10)
    clock[0] = KICKOFF + timedelta(hours=1)
    engine.run_once()
    scheduler_module.capture_weekly.assert_not_called()
    job = accuracy_jobs.job(2026, "weekly", "capture")
    assert job["state"] == "error"
    assert "interrupted" in job["last_error"]
    assert job["last_success_at"] is None


def test_capture_failures_back_off_and_do_not_expose_upstream_secrets(engine, clock, caplog):
    scheduler_module.capture_weekly.side_effect = RuntimeError("secret-cookie-value")
    engine.run_once()
    failed = accuracy_jobs.job(2026, "weekly", "capture")
    assert failed["state"] == "error"
    assert failed["last_success_at"] is None
    assert "secret-cookie-value" not in caplog.text
    assert "secret-cookie-value" not in str(failed)
    clock[0] += timedelta(minutes=2)
    engine.run_once()
    assert scheduler_module.capture_weekly.call_count == 1
    scheduler_module.capture_weekly.side_effect = None
    clock[0] += timedelta(minutes=14)
    engine.run_once()
    assert accuracy_jobs.job(2026, "weekly", "capture")["state"] == "success"


def test_schedule_errors_back_off_and_remain_visible(engine, clock, monkeypatch):
    fetch = Mock(side_effect=OSError("offline"))
    monkeypatch.setattr(engine, "schedule", fetch)
    engine.run_once()
    assert "schedule unavailable" in accuracy_jobs.status(2026, "weekly")["worker_error"]
    clock[0] += timedelta(minutes=1)
    engine.run_once()
    assert fetch.call_count == 1
    clock[0] += timedelta(minutes=15)
    engine.run_once()
    assert fetch.call_count == 2


def test_stopped_or_disabled_worker_does_no_work(engine, monkeypatch):
    engine.stop()
    engine.run_once()
    scheduler_module.capture_weekly.assert_not_called()
    monkeypatch.setenv("FANTASY_AUTOMATION_ENABLED", "false")
    AccuracyScheduler().run_once()
    scheduler_module.capture_weekly.assert_not_called()


def test_public_and_current_local_leagues_are_automatic_targets(engine, clock, monkeypatch):
    config = SimpleNamespace(league_id=456, season=2026, espn_s2="test-secret", swid="test-swid")
    monkeypatch.setattr(scheduler_module, "current_local_config", lambda: config)
    accuracy_jobs.register(123, 2026, "public")
    accuracy_jobs.register(999, 2026, "local")  # Old/private configuration must not be used.
    accuracy_jobs.register(124, 2025, "public")
    capture = Mock(return_value={"saved_count": 10})
    monkeypatch.setattr(scheduler_module, "capture_league", capture)
    engine.run_once()
    assert {call.args[1]["scope"] for call in capture.call_args_list} == {"espn:123", "espn:456"}
    assert accuracy_jobs.job(2026, "espn:123", "capture")["result"]["saved_count"] == 10
    with prediction_history.connect() as connection:
        contents = "\n".join(connection.iterdump())
    assert "test-secret" not in contents
    assert "test-swid" not in contents


def test_connecting_public_league_registers_only_successful_connections(monkeypatch):
    from app.routes import espn
    league = SimpleNamespace()
    monkeypatch.setattr(espn, "get_league", lambda **_: league)
    assert espn.get_public_league(123, 2026) is league
    assert accuracy_jobs.targets() == [{"scope": "espn:123", "season": 2026, "mode": "public"}]
    monkeypatch.setattr(espn, "get_league", Mock(side_effect=RuntimeError("Cannot connect")))
    with pytest.raises(RuntimeError):
        espn.get_public_league(456, 2026)
    assert len(accuracy_jobs.targets()) == 1


def test_league_capture_uses_same_pool_logic_and_runtime_credentials(monkeypatch, clock):
    from app.routes import espn
    from app.integrations import espn_fantasy
    league = SimpleNamespace()
    getter = Mock(return_value=league)
    monkeypatch.setattr(espn_fantasy, "get_league", getter)
    pool = Mock(return_value=(SimpleNamespace(), 11))
    monkeypatch.setattr(espn, "project_league_players", pool)
    config = SimpleNamespace(espn_s2="secret", swid="swid")
    service, games = SimpleNamespace(), schedule()
    assert capture_league(service, {"scope": "espn:123", "season": 2026, "mode": "local"},
                          10, games, config) == {"saved_count": 11}
    getter.assert_called_once_with(league_id=123, year=2026, espn_s2="secret", swid="swid")
    assert pool.call_args.kwargs["strict_history"] is True
    assert pool.call_args.kwargs["history_schedule"] is games
    assert pool.call_args.kwargs["service"] is service


class FakeData:
    def get_projection_roster(self, **_):
        return pd.DataFrame([{"player_id": position, "player_name": position, "position": position,
                              "team": "BUF", "season": 2026, "week": 9}
                             for position in ("QB", "RB", "WR", "TE", "K")]), 9

    def get_week_depth_chart(self, **_):
        return None


class FakeService:
    model_revision = "checkpoint-revision"
    data = FakeData()

    def __init__(self, clock):
        self.clock = clock
        self.requests = []
        self.fail_position = None

    def project_requests(self, position, requests):
        if position == self.fail_position:
            raise ValueError("Missing model")
        self.requests.extend(requests)
        return ProjectionSlateResult(projections=[PlayerProjection(
            request=request, position=position, predicted_points=20) for request in requests],
            skipped=[], generated_at=self.clock[0])


def test_weekly_capture_all_six_positions_target_week_and_kickoff_lock(clock):
    service = FakeService(clock)
    result = capture_weekly(service, 2026, 10, {"BUF", "MIA"}, schedule())
    assert result["saved_count"] == 7  # Five BUF players plus two D/STs.
    rows = prediction_history.rows(2026, "weekly")
    assert {row["position"] for row in rows} == {"QB", "RB", "WR", "TE", "K", "DST"}
    assert {request.upcoming_week for request in service.requests} == {10}
    clock[0] = KICKOFF
    assert capture_weekly(service, 2026, 10, {"BUF", "MIA"}, schedule())["saved_count"] == 0
    assert len(prediction_history.rows(2026, "weekly")) == 7


def test_partial_capture_preserves_successful_positions_but_reports_failure(clock):
    service = FakeService(clock)
    service.fail_position = "WR"
    with pytest.raises(RuntimeError, match="WR"):
        capture_weekly(service, 2026, 10, {"BUF", "MIA"}, schedule())
    assert len(prediction_history.rows(2026, "weekly")) == 6


@pytest.mark.parametrize("kickoff,expected", [
    ("2026-11-08T14:30:00+00:00", "2026-11-09T13:00:00+00:00"),  # Overseas, next day.
    ("2026-11-13T01:15:00+00:00", "2026-11-13T13:15:00+00:00"),  # Night game: 12h minimum.
    ("2026-10-25T17:00:00+00:00", "2026-10-26T12:00:00+00:00"),  # Daylight time.
])
def test_next_morning_respects_eastern_time_and_twelve_hour_minimum(kickoff, expected):
    assert next_morning(kickoff) == datetime.fromisoformat(expected)


def test_automatic_results_wait_for_morning_after_twelve_hours_have_passed(clock):
    capture_weekly(FakeService(clock), 2026, 10, {"BUF", "MIA"}, schedule())
    completed = schedule(home_score=21, away_score=10, result=11)
    stats = pd.DataFrame([{"season": 2026, "week": 10, "position": "QB", "season_type": "REG",
                           "player_id": "QB", "recent_team": "BUF", "fantasy_points_ppr": 16}])
    # At 2 a.m. Eastern, the 12-hour rule alone is met; scheduled sync must wait until 8.
    early = datetime(2026, 11, 9, 7, tzinfo=UTC)
    result = actuals_module.reconcile(prediction_history, 2026, "weekly", completed,
                                      stats, {}, now=early, automatic=True)
    assert result["checked_count"] == 0
    result = actuals_module.reconcile(prediction_history, 2026, "weekly", completed,
                                      stats, {}, now=early, automatic=False)
    assert result["checked_count"] == 1


def test_private_capture_status_tracks_disabled_configuration(clock):
    accuracy_jobs.register(456, 2026, "local")
    status = accuracy_jobs.status(2026, "espn:456")
    assert status["registered"]
    assert not status["capture_enabled"]
    assert "configuration enabled" in status["note"]


def test_failed_sync_preserves_last_success_and_exposes_retry(clock):
    jobs_module.run_tracked_sync(2026, "weekly", lambda: {"checked_count": 1, "updated_count": 1})
    succeeded = accuracy_jobs.job(2026, "weekly", "sync")["last_success_at"]
    clock[0] += timedelta(hours=6)
    with pytest.raises(OSError):
        jobs_module.run_tracked_sync(2026, "weekly", Mock(side_effect=OSError("offline")))
    failed = accuracy_jobs.job(2026, "weekly", "sync")
    assert failed["state"] == "error"
    assert failed["last_success_at"] == succeeded
    assert failed["next_run_at"] == (clock[0] + timedelta(minutes=15)).isoformat()


def test_sync_runs_next_morning_and_reuses_persisted_six_hour_cadence(engine, clock, monkeypatch):
    capture_weekly(FakeService(clock), 2026, 10, {"BUF", "MIA"}, schedule())
    sync = Mock(return_value={"checked_count": 7, "updated_count": 7})
    monkeypatch.setattr(scheduler_module, "sync_actuals", sync)
    clock[0] = datetime(2026, 11, 9, 12, 59, tzinfo=UTC)
    engine.run_once()
    sync.assert_not_called()
    clock[0] += timedelta(minutes=1)
    engine.run_once()
    assert sync.call_count == 1
    assert sync.call_args.kwargs["automatic"] is True
    assert accuracy_jobs.job(2026, "weekly", "sync")["last_success_at"] == clock[0].isoformat()
    clock[0] += timedelta(hours=1)
    engine.run_once()
    assert sync.call_count == 1
    clock[0] += timedelta(hours=5)
    engine.run_once()
    assert sync.call_count == 2


def test_no_auto_sync_for_empty_or_old_history(engine, clock, monkeypatch):
    sync = Mock()
    monkeypatch.setattr(scheduler_module, "sync_actuals", sync)
    engine.run_once()
    sync.assert_not_called()
    capture_weekly(FakeService(clock), 2026, 10, {"BUF", "MIA"}, schedule())
    clock[0] += timedelta(days=15)
    engine.run_once()
    sync.assert_not_called()


def test_automation_status_is_read_only_and_manual_sync_records_status(monkeypatch, clock):
    from app.routes import accuracy
    monkeypatch.setattr(accuracy, "sync_actuals", lambda *_: {"updated_count": 2, "checked_count": 3})
    client = TestClient(main.app)
    accuracy_jobs.register(123, 2026, "public")
    response = client.post("/api/accuracy/2026/sync?league_id=123")
    assert response.status_code == 200
    body = client.get("/api/accuracy/2026/automation?league_id=123").json()
    assert body["enabled"] is True
    assert body["registered"] is True
    assert body["sync"]["result"] == {"updated_count": 2, "checked_count": 3}
    assert "scope" not in body["sync"]
    assert "secret" not in str(body)
    assert client.get("/api/accuracy/2026/automation?league_id=456").json()["registered"] is False


def test_manual_sync_cannot_overlap_background_capture(clock):
    with operation_lock():
        assert TestClient(main.app).post("/api/accuracy/2026/sync").status_code == 409


def test_worker_lifespan_starts_and_stops_without_waiting_for_jobs(monkeypatch):
    worker = SimpleNamespace(start=Mock(), stop=Mock())
    monkeypatch.setattr(main, "AccuracyScheduler", lambda: worker)
    with TestClient(main.app) as client:
        worker.start.assert_called_once()
        assert client.get("/api/health/").status_code == 200
        worker.stop.assert_not_called()
    worker.stop.assert_called_once()


def test_service_refreshes_only_after_six_hours(monkeypatch, clock):
    service = SimpleNamespace(loaded_at=monotonic())
    getter = Mock(return_value=service)
    monkeypatch.setattr(scheduler_module.projection_services, "get", getter)
    worker = AccuracyScheduler()
    assert worker.service(2026) is service
    getter.assert_called_once_with(2026)
    getter.reset_mock()
    service.loaded_at -= 7 * 3600
    worker.service(2026)
    assert getter.call_args_list[1].kwargs == {"refresh": True}


@pytest.fixture
def warmup(engine, monkeypatch):
    monkeypatch.setenv("FANTASY_PRECOMPUTE_ENABLED", "true")
    accuracy_jobs.register(123, 2026, "public")
    operation = Mock(return_value={"team_count": 2, "player_count": 100, "saved_count": 100, "week": 10})
    monkeypatch.setattr(scheduler_module, "capture_league", Mock(return_value={"saved_count": 4}))
    monkeypatch.setattr(scheduler_module, "precompute_league", operation)
    return operation


def test_warmup_runs_outside_capture_window_and_repeats_every_thirty_minutes(engine, clock, warmup):
    clock[0] = KICKOFF - timedelta(days=2)
    engine.run_once()
    assert warmup.call_count == 1
    scheduler_module.capture_weekly.assert_not_called()
    assert accuracy_jobs.status(2026, "espn:123")["precompute"]["result"]["player_count"] == 100
    clock[0] += timedelta(minutes=29)
    engine.run_once()
    assert warmup.call_count == 1
    clock[0] += timedelta(minutes=2)
    engine.run_once()
    assert warmup.call_count == 2


def test_restart_warms_process_data_even_with_recent_durable_success(engine, clock, warmup, monkeypatch):
    engine.run_once()
    restarted = AccuracyScheduler(clock=lambda: clock[0])
    monkeypatch.setattr(restarted, "schedule", engine.schedule)
    monkeypatch.setattr(restarted, "service", engine.service)
    restarted.run_once()
    assert warmup.call_count == 2


def test_warmup_failures_back_off_across_restart_without_leaking_details(engine, clock, warmup, monkeypatch, caplog):
    warmup.side_effect = RuntimeError("private-cookie")
    engine.run_once()
    assert warmup.call_count == 1
    restarted = AccuracyScheduler(clock=lambda: clock[0])
    monkeypatch.setattr(restarted, "schedule", engine.schedule)
    monkeypatch.setattr(restarted, "service", engine.service)
    clock[0] += timedelta(minutes=14)
    restarted.run_once()
    assert warmup.call_count == 1
    clock[0] += timedelta(minutes=1)
    warmup.side_effect = None
    restarted.run_once()
    assert warmup.call_count == 2
    assert accuracy_jobs.job(2026, "espn:123", "precompute")["state"] == "success"
    assert "private-cookie" not in caplog.text


def test_disabled_and_offseason_warmup_do_not_load_models(engine, clock, warmup, monkeypatch):
    clock[0] = KICKOFF - timedelta(days=8)
    engine.run_once()
    warmup.assert_not_called()
    clock[0] = KICKOFF + timedelta(days=2)
    engine.run_once()
    warmup.assert_not_called()
    clock[0] = KICKOFF - timedelta(days=1)
    monkeypatch.setenv("FANTASY_PRECOMPUTE_ENABLED", "false")
    engine.run_once()
    warmup.assert_not_called()


def test_capture_is_not_delayed_by_warmup_failure(engine, clock, warmup):
    warmup.side_effect = RuntimeError("Failed warmup")
    engine.run_once()
    assert accuracy_jobs.job(2026, "weekly", "capture")["state"] == "success"
    assert accuracy_jobs.job(2026, "espn:123", "precompute")["state"] == "error"


def test_week_rollover_bypasses_previous_weeks_warmup_timer(engine, clock, warmup, monkeypatch):
    engine.run_once()
    games = schedule(week=11)
    monkeypatch.setattr(engine, "schedule", lambda *_: games)
    clock[0] += timedelta(minutes=1)
    engine.run_once()
    assert warmup.call_count == 2
    assert accuracy_jobs.job(2026, "espn:123", "precompute")["week"] == 11


def test_warmup_skips_unavailable_saved_and_old_season_targets(engine, clock, warmup, monkeypatch):
    monkeypatch.setenv("FANTASY_AUTH_ENABLED", "true")
    accuracy_jobs.register(456, 2026, "saved")
    accuracy_jobs.register(789, 2026, "saved")
    accuracy_jobs.register(222, 2025, "public")
    monkeypatch.setattr(scheduler_module.accounts, "connections", lambda: [
        {"league_id": 456, "season": 2026, "mode": "private", "status": "expired"}])
    engine.run_once()
    assert [call.args[1]["scope"] for call in warmup.call_args_list] == ["espn:123"]
