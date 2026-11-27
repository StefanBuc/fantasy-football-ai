from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from app.routes import accuracy as accuracy_route
from app.services import prediction_history as history_module
from app.services import prediction_actuals as actuals_module
from app.services.prediction_history import PredictionHistory, game_times, prediction_history
from app.services.prediction_actuals import reconcile

UTC = timezone.utc
PREGAME = datetime(2026, 11, 8, 17, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 8, 18, tzinfo=UTC)  # 13:00 Eastern, after DST ends.


def schedule(**updates):
    game = {"season": 2026, "week": 10, "game_type": "REG", "home_team": "BUF",
            "away_team": "MIA", "gameday": "2026-11-08", "gametime": "13:00",
            "home_score": None, "away_score": None, "result": None}
    return pd.DataFrame([{**game, **updates}])


def sample(**updates):
    return {"player_id": "qb-1", "player_name": "Test QB", "position": "QB", "team": "BUF",
            "opponent_team": "MIA", "predicted_points": 20.0, "projection_method": "model", **updates}


def record(monkeypatch, *, samples=None, games=None, now=PREGAME, generated_at=None,
           scope="espn:123", revision="revision-a", week=10):
    monkeypatch.setattr(history_module, "utc_now", lambda: now)
    prediction_history.record(season=2026, week=week, samples=samples or [sample()],
                              schedule=games if games is not None else schedule(),
                              generated_at=generated_at or now, scope=scope, model_revision=revision)


def weekly(**updates):
    return pd.DataFrame([{"player_id": "qb-1", "position": "QB", "season": 2026, "week": 10,
                          "season_type": "REG", "recent_team": "BUF", "fantasy_points_ppr": 16.0, **updates}])


def completed(**updates):
    return schedule(home_score=21, away_score=10, result=11, **updates)


def test_latest_pregame_prediction_is_frozen_at_kickoff(monkeypatch):
    record(monkeypatch)
    record(monkeypatch, now=PREGAME + timedelta(minutes=30), samples=[sample(predicted_points=23)],
           revision="revision-b")
    record(monkeypatch, now=KICKOFF, samples=[sample(predicted_points=99)])
    record(monkeypatch, now=KICKOFF + timedelta(days=1), generated_at=PREGAME,
           samples=[sample(predicted_points=100)])
    rows = prediction_history.rows(2026, "espn:123")
    assert len(rows) == 1
    assert rows[0]["predicted_points"] == 23
    assert rows[0]["model_version"] == "QB_model_v4"
    assert rows[0]["model_revision"] == "revision-b"
    assert rows[0]["kickoff"] == KICKOFF.isoformat()


def test_cached_pregame_result_records_but_older_cache_cannot_replace_newer(monkeypatch):
    record(monkeypatch, generated_at=PREGAME - timedelta(hours=1))
    record(monkeypatch, samples=[sample(predicted_points=25)])
    record(monkeypatch, now=PREGAME + timedelta(minutes=1),
           generated_at=PREGAME - timedelta(hours=1), samples=[sample(predicted_points=10)])
    assert prediction_history.rows(2026, "espn:123")[0]["predicted_points"] == 25


@pytest.mark.parametrize("games", [pd.DataFrame(), schedule(gametime=None), schedule(game_type="POST"),
                                        schedule(away_team="NYJ")])
def test_missing_or_mismatched_schedule_never_guesses_pregame(monkeypatch, games):
    record(monkeypatch, games=games)
    assert prediction_history.rows(2026, "espn:123") == []


def test_rejects_nonfinite_skipped_unmatched_and_future_timestamps(monkeypatch):
    record(monkeypatch, samples=[sample(predicted_points=float("nan")), sample(predicted_points=None),
                                sample(player_id=None), sample(predicted_points=float("inf"))])
    record(monkeypatch, generated_at=PREGAME + timedelta(seconds=1))
    record(monkeypatch, generated_at=PREGAME.replace(tzinfo=None))
    assert prediction_history.rows(2026, "espn:123") == []


def test_timezone_handles_summer_and_team_aliases():
    times = game_times(schedule(gameday="2026-09-13", home_team="LAR", away_team="WSH"), 2026, 10)
    assert times["LA"][:2] == ("WAS", datetime(2026, 9, 13, 17, tzinfo=UTC))


def test_history_survives_cache_clear_and_new_store_instance(monkeypatch):
    from app.services.disk_cache import disk_cache
    record(monkeypatch)
    disk_cache.put("weekly", "sample", b"cached", 3600)
    disk_cache.clear("weekly")
    reopened = PredictionHistory(prediction_history.path)
    assert reopened.rows(2026, "espn:123")[0]["predicted_points"] == 20


def test_same_cached_generation_can_capture_latest_injury_adjustment(monkeypatch):
    record(monkeypatch)
    record(monkeypatch, now=PREGAME + timedelta(minutes=10), generated_at=PREGAME,
           samples=[sample(predicted_points=0)])
    assert prediction_history.rows(2026, "espn:123")[0]["predicted_points"] == 0


def test_actuals_metrics_scope_and_stat_corrections(monkeypatch):
    record(monkeypatch, samples=[sample(), sample(player_id="qb-2", predicted_points=10)])
    record(monkeypatch, samples=[sample(predicted_points=100)], scope="espn:456")
    record(monkeypatch, samples=[sample(predicted_points=50)], scope="weekly")
    stats = pd.concat([weekly(), weekly(player_id="qb-2", fantasy_points_ppr=14)])
    result = reconcile(prediction_history, 2026, "espn:123", completed(), stats, {},
                       now=KICKOFF + timedelta(days=1))
    assert result == {"updated_count": 2, "checked_count": 2}
    report = prediction_history.report(2026, "espn:123")
    assert report["summary"] == {"saved": 2, "scored": 2, "pending": 0, "mae": 4, "bias": 0}
    assert report["by_model"][0]["model_revision"] == "revision-a"
    assert report["by_model"][0]["mae"] == 4
    assert prediction_history.report(2026, "espn:456")["summary"]["scored"] == 0
    # Re-sync applies corrections without duplicating either predictions or scores.
    reconcile(prediction_history, 2026, "espn:123", completed(), weekly(fantasy_points_ppr=18), {},
              now=KICKOFF + timedelta(days=2))
    assert prediction_history.report(2026, "espn:123")["summary"]["mae"] == 3
    assert prediction_history.rows(2026, "espn:123")[0]["predicted_points"] == 20


@pytest.mark.parametrize("games,stats,now", [
    (schedule(), weekly(), KICKOFF + timedelta(days=1)),
    (completed(), weekly(), KICKOFF + timedelta(hours=3)),
    (completed(), weekly(season_type="POST"), KICKOFF + timedelta(days=1)),
    (completed(), weekly(recent_team="NYJ"), KICKOFF + timedelta(days=1)),
    (completed(), weekly(fantasy_points_ppr=float("nan")), KICKOFF + timedelta(days=1)),
    (completed(), pd.DataFrame(), KICKOFF + timedelta(days=1)),
])
def test_partial_missing_live_or_wrong_game_stats_stay_pending(monkeypatch, games, stats, now):
    record(monkeypatch)
    assert reconcile(prediction_history, 2026, "espn:123", games, stats, {}, now=now)["checked_count"] == 0
    assert prediction_history.report(2026, "espn:123")["summary"]["mae"] is None


def test_duplicate_actuals_stay_pending(monkeypatch):
    record(monkeypatch)
    assert reconcile(prediction_history, 2026, "espn:123", completed(),
                     pd.concat([weekly(), weekly()]), {}, now=KICKOFF + timedelta(days=1))["checked_count"] == 0


def test_kicker_and_dst_use_app_scoring_and_normalized_ids(monkeypatch):
    record(monkeypatch, samples=[sample(player_id="TEAM:BUF", position="D/ST", predicted_points=7),
                                sample(player_id="k-1", position="K", predicted_points=9)])
    special = {"DST": pd.DataFrame([{"season": 2026, "week": 10, "entity_id": "BUF",
                                     "team": "BUF", "fantasy_points": -2.0}]),
               "K": pd.DataFrame([{"season": 2026, "week": 10, "entity_id": "k-1",
                                   "team": "BUF", "fantasy_points": 0.0}])}
    # The offensive import can contain K rows; they must not collide with kicker scoring.
    reconcile(prediction_history, 2026, "espn:123", completed(), weekly(player_id="k-1", position="K"),
              special, now=KICKOFF + timedelta(days=1))
    report = prediction_history.report(2026, "espn:123")
    assert report["summary"]["scored"] == 2
    assert report["summary"]["mae"] == 9
    assert report["records"][0]["player_id"] == "BUF"


def test_accuracy_api_filter_pagination_and_trend(monkeypatch):
    record(monkeypatch, samples=[sample(), sample(player_id="rb-1", position="RB")])
    record(monkeypatch, samples=[sample(predicted_points=30)], week=11,
           games=schedule(week=11, gameday="2026-11-15"))
    client = TestClient(app)
    body = client.get("/api/accuracy/2026?league_id=123&position=QB&week=10&limit=1").json()
    assert body["summary"]["saved"] == 1
    assert [row["week"] for row in body["weekly_trend"]] == [10, 11]
    assert len(body["records"]) == 1
    assert "scope" not in body["records"][0]
    assert client.get("/api/accuracy/2026?league_id=123&limit=1&offset=1").json()["offset"] == 1
    assert client.get("/api/accuracy/2026").json()["summary"]["saved"] == 0
    for query in ("week=19", "position=FLEX", "limit=0", "offset=-1", "league_id=0"):
        assert client.get(f"/api/accuracy/2026?{query}").status_code == 422


def test_sync_does_not_download_for_empty_history(monkeypatch):
    monkeypatch.setattr(actuals_module.nfl, "import_schedules", lambda *_: pytest.fail("Unexpected download"))
    assert TestClient(app).post("/api/accuracy/2026/sync").json()["updated_count"] == 0


def test_sync_downloads_results_without_loading_projection_service(monkeypatch):
    record(monkeypatch)
    monkeypatch.setattr(actuals_module, "utc_now", lambda: KICKOFF + timedelta(days=1))
    monkeypatch.setattr(actuals_module.nfl, "import_schedules", lambda *_: completed())
    monkeypatch.setattr(actuals_module.NFLData, "_load_weekly_player_data", lambda *_: weekly())
    monkeypatch.setattr(actuals_module, "load_special_teams_weekly", lambda *_: pytest.fail("Unneeded PBP download"))
    response = TestClient(app).post("/api/accuracy/2026/sync?league_id=123")
    assert response.status_code == 200
    assert response.json()["updated_count"] == 1
    assert prediction_history.report(2026, "espn:123")["summary"]["mae"] == 4


def test_sync_failure_preserves_history_and_read_does_no_network(monkeypatch):
    record(monkeypatch)
    monkeypatch.setattr(actuals_module.nfl, "import_schedules", lambda *_: (_ for _ in ()).throw(OSError("offline")))
    client = TestClient(app)
    assert client.post("/api/accuracy/2026/sync?league_id=123").status_code == 503
    assert client.get("/api/accuracy/2026?league_id=123").json()["summary"]["saved"] == 1


def test_database_failure_is_visible_on_accuracy_page(monkeypatch):
    # A directory cannot be opened as a SQLite file.
    monkeypatch.setattr(prediction_history, "path", prediction_history.path.parent)
    assert TestClient(app).get("/api/accuracy/2026").status_code == 503


def test_failed_recording_does_not_hide_projection(monkeypatch):
    monkeypatch.setattr(prediction_history, "path", prediction_history.path.parent)
    history_module.record_predictions(SimpleNamespace(data=SimpleNamespace(schedule=schedule())),
                                     season=2026, week=10, samples=[sample()], generated_at=PREGAME)


def test_concurrent_sync_is_rejected():
    accuracy_route.sync_lock.acquire()
    try:
        assert TestClient(app).post("/api/accuracy/2026/sync").status_code == 409
    finally:
        accuracy_route.sync_lock.release()


def test_weekly_projection_cache_hits_are_archived_once(monkeypatch):
    from app.services.weekly_projection_service import WeeklyProjectionService
    from app.services.result_cache import ResultCache
    from app.services.projection_types import PlayerProjection, PlayerProjectionRequest, ProjectionSlateResult

    monkeypatch.setattr(history_module, "utc_now", lambda: PREGAME)
    service = WeeklyProjectionService.__new__(WeeklyProjectionService)
    service.season = 2026
    service.data = SimpleNamespace(schedule=schedule())
    service.model_revision = "checkpoint-hash"
    service.weekly_cache = ResultCache(name="test-history")
    result = ProjectionSlateResult(projections=[PlayerProjection(
        request=PlayerProjectionRequest(player_id="qb-1", player_name="Test QB", team="BUF",
                                        opponent_team="MIA", season=2026, upcoming_week=10),
        position="QB", predicted_points=20)], skipped=[], generated_at=PREGAME)
    calls = []

    def build(*args):
        calls.append(args)
        return result

    monkeypatch.setattr(service, "_project_week_uncached", build)
    assert service.project_week(10, "QB") == result
    assert service.project_week(10, "QB") == result
    assert len(calls) == 1
    assert len(prediction_history.rows(2026, "weekly")) == 1
    assert prediction_history.rows(2026, "weekly")[0]["model_revision"] == "checkpoint-hash"


def test_espn_cached_response_archives_displayed_injury_adjustment(monkeypatch):
    from app.routes import espn
    from app.integrations.espn_roster_projection import ESPNRosterProjection

    monkeypatch.setattr(history_module, "utc_now", lambda: PREGAME)
    player = SimpleNamespace(playerId=501, name="Test QB", position="QB", lineupSlot="QB",
                             injuryStatus="OUT", stats={10:{'projected_breakdown':{'passingYards':250}}})
    league = SimpleNamespace(settings=SimpleNamespace(name="Test League"), teams=[
        SimpleNamespace(team_id=1, team_name="Team", roster=[player])])
    item = ESPNRosterProjection(espn_id=501, player_id="qb-1", player_name="Test QB", position="QB",
                                lineup_slot="QB", team="BUF", opponent_team="MIA",
                                predicted_points=20, status="projected", projection_method="model")
    entry = SimpleNamespace(generated_at=PREGAME, roster_week=10, team_projections={1: (item,)})
    monkeypatch.setattr(espn.projection_cache, "get_or_create", lambda **_: (entry, True))
    service = SimpleNamespace(data=SimpleNamespace(schedule=schedule()), model_revision="hash", generation="hash")
    response = espn.build_team_projection_response(league, 123, 2026, 1, 10, service)
    assert response.cache_hit
    assert response.players[0].predicted_points == 0
    assert prediction_history.rows(2026, "espn:123")[0]["predicted_points"] == 0
    assert prediction_history.rows(2026, "espn:123")[0]["espn_predicted_points"] == 10
    player.injuryStatus = "ACTIVE"
    monkeypatch.setattr(history_module, "utc_now", lambda: KICKOFF)
    response = espn.build_team_projection_response(league, 123, 2026, 1, 10, service)
    assert response.players[0].predicted_points == 20
    assert prediction_history.rows(2026, "espn:123")[0]["predicted_points"] == 0
