from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from main import app
from app.services import live_scores, projection_ranges, prediction_history as history_module
from app.services.prediction_history import prediction_history
from app.services.score_presentation import prediction_display
from app.schemas.espn import LivePlayerRequest

UTC = timezone.utc
PREGAME = datetime(2026, 11, 8, 17, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 8, 18, tzinfo=UTC)


@pytest.fixture(autouse=True)
def live_cache_isolation():
    live_scores.game_cache.clear()
    live_scores.score_cache.clear()
    yield
    live_scores.game_cache.clear()
    live_scores.score_cache.clear()


@pytest.fixture
def ranges(tmp_path, monkeypatch):
    path = tmp_path / 'ranges.json'
    fitted = projection_ranges.fit_residual_range(np.linspace(-10, 10, 200), np.linspace(-9, 9, 100))
    path.write_text(json.dumps({"format_version": 1, "season": 2025, "positions": {
        "QB": {"checkpoint_sha256": "checkpoint", "methods": {"model": fitted}}}}))
    monkeypatch.setattr(projection_ranges, "RANGE_PATH", path)
    return path


def game_schedule():
    return pd.DataFrame([{"season": 2026, "week": 10, "game_type": "REG", "home_team": "BUF",
                          "away_team": "MIA", "gameday": "2026-11-08", "gametime": "13:00"}])


def player(**updates):
    return {"player_id": "qb-1", "player_name": "QB", "position": "QB", "team": "BUF",
            "opponent_team": "MIA", "predicted_points": 20.0, "projection_method": "model", **updates}


def save(monkeypatch, **kwargs):
    monkeypatch.setattr(history_module, "utc_now", lambda: PREGAME)
    prediction_history.record(season=2026, week=10, samples=[player(**kwargs)], schedule=game_schedule(),
        generated_at=PREGAME, model_revision="revision", model_hashes={"QB": "checkpoint"}, scope="espn:123")


def fantasy(points=0, season=2026, week=10, **updates):
    entry = {"seasonId": season, "scoringPeriodId": week, "statSourceId": 0,
             "statSplitTypeId": 1, "appliedTotal": points}
    entry.update(updates)
    return {"players": [{"id": 501, "player": {"id": 501, "proTeamId": 2, "stats": [entry]}}]}


def scoreboard(state="in", completed=False, name="STATUS_IN_PROGRESS"):
    return {"season": {"year": 2026, "type": 2}, "week": {"number": 10}, "events": [{
        "date": KICKOFF.isoformat(), "status": {"type": {"state": state, "completed": completed,
        "name": name, "shortDetail": "Q2 3:20"}}, "competitions": [{"competitors": [
        {"team": {"abbreviation": "BUF"}}, {"team": {"abbreviation": "MIA"}}]}]}]}


def descriptor():
    return LivePlayerRequest(espn_id=501, player_id="qb-1", position="QB", team="BUF")


def test_bounds_fit_uses_calibration_only_and_evaluates_separate_games():
    first = projection_ranges.fit_residual_range(np.arange(-100, 100), np.arange(-50, 50))
    second = projection_ranges.fit_residual_range(np.arange(-100, 100), np.arange(1000, 1100))
    assert first["low_offset"] == second["low_offset"]
    assert first["high_offset"] == second["high_offset"]
    assert first["validation_coverage"] > second["validation_coverage"]
    assert not projection_ranges.fit_residual_range([1, 2], [3, 4])["ready"]


def test_ranges_require_exact_checkpoint_and_allow_negative_floors(ranges):
    valid = projection_ranges.estimate_range(2, "QB", "model", {"QB": "checkpoint"})
    assert valid["floor_points"] < 0 < 2 < valid["ceiling_points"]
    assert "validation games" in valid["range_note"]
    assert projection_ranges.estimate_range(20, "QB", "model", {"QB": "different"})["floor_points"] is None
    assert projection_ranges.estimate_range(20, "QB", "position_average", {"QB": "checkpoint"})["floor_points"] is None


def test_range_corruption_or_missing_artifact_does_not_hide_predictions(ranges):
    ranges.write_text('invalid-json')
    assert projection_ranges.estimate_range(20, "QB", "model", {"QB": "checkpoint"})["floor_points"] is None


def test_pregame_ranges_and_predictions_freeze_together(monkeypatch, ranges):
    save(monkeypatch)
    original = prediction_history.rows(2026, "espn:123")[0]
    assert original["floor_points"] < 20 < original["ceiling_points"]
    monkeypatch.setattr(history_module, "utc_now", lambda: KICKOFF + timedelta(minutes=30))
    prediction_history.record(season=2026, week=10, samples=[player(predicted_points=999)],
        schedule=game_schedule(), generated_at=PREGAME, model_revision="revision-2",
        model_hashes={"QB": "checkpoint"}, scope="espn:123")
    assert prediction_history.rows(2026, "espn:123")[0] == original
    service = SimpleNamespace(data=SimpleNamespace(schedule=game_schedule()), model_hashes={"QB": "different"})
    displayed = prediction_display(service, 2026, 10, "espn:123", [player(predicted_points=999)])[0]
    assert displayed["pregame_predicted_points"] == 20
    assert displayed["floor_points"] == original["floor_points"]


def test_live_parse_uses_official_status_instead_of_elapsed_hours():
    assert live_scores.parse_games(scoreboard(), 2026, 10)["BUF"]["game_state"] == "live"
    assert live_scores.parse_games(scoreboard("post", True, "STATUS_FINAL"), 2026, 10)["BUF"]["game_state"] == "final"
    assert live_scores.parse_games(scoreboard("pre", False, "STATUS_POSTPONED"), 2026, 10)["BUF"]["game_state"] == "postponed"
    with pytest.raises(ValueError):
        live_scores.parse_games(scoreboard(), 2026, 11)


@pytest.mark.parametrize("value", [0, -3.25, 12.5])
def test_actual_points_preserve_zero_negative_and_fractional_scores(value):
    assert live_scores.parse_fantasy_players(fantasy(value), 2026, 10)[501]["points"] == value


@pytest.mark.parametrize("payload", [fantasy(25, season=2025), fantasy(25, week=9),
    fantasy(25, statSourceId=1), fantasy(None), fantasy(float('nan')), fantasy(float('inf'))])
def test_projections_wrong_weeks_and_missing_values_are_never_live_zero(payload):
    assert live_scores.parse_fantasy_players(payload, 2026, 10)[501]["points"] is None


def test_duplicate_actual_entries_are_not_silently_added():
    payload = fantasy(12)
    payload["players"][0]["player"]["stats"] *= 2
    assert live_scores.parse_fantasy_players(payload, 2026, 10)[501]["points"] is None


def test_live_response_is_lightweight_and_preserves_frozen_prediction(monkeypatch, ranges):
    save(monkeypatch)
    original = prediction_history.rows(2026, "espn:123")[0]
    monkeypatch.setattr(live_scores, "fetch_games", lambda *_: live_scores.parse_games(scoreboard(), 2026, 10))
    provider = Mock(return_value=live_scores.parse_fantasy_players(fantasy(7.4), 2026, 10))
    monkeypatch.setattr(live_scores, "fetch_fantasy_scores", provider)
    response = live_scores.live_response(SimpleNamespace(), 2026, 10, [descriptor()], "espn:123")
    row = response["players"][0]
    assert row["live_points"] == 7.4
    assert row["pregame_predicted_points"] == 20
    assert row["floor_points"] == original["floor_points"]
    live_scores.live_response(SimpleNamespace(), 2026, 10, [descriptor()], "espn:123")
    assert provider.call_count == 1
    assert prediction_history.rows(2026, "espn:123")[0] == original


def test_pregame_feed_does_not_download_player_stats(monkeypatch):
    monkeypatch.setattr(live_scores, "fetch_games", lambda *_: live_scores.parse_games(scoreboard("pre"), 2026, 10))
    provider = Mock(side_effect=AssertionError("Unnecessary player download"))
    monkeypatch.setattr(live_scores, "fetch_fantasy_scores", provider)
    league = Mock(side_effect=AssertionError("Unnecessary league download"))
    result = live_scores.live_response(league, 2026, 10, [descriptor()], "espn:123")
    assert result["players"][0]["game_state"] == "pregame"
    assert result["players"][0]["live_points"] is None
    provider.assert_not_called()
    league.assert_not_called()


def test_provider_failure_shows_missing_scores_without_fabricating_predictions(monkeypatch):
    monkeypatch.setattr(live_scores, "fetch_games", lambda *_: live_scores.parse_games(scoreboard(), 2026, 10))
    monkeypatch.setattr(live_scores, "fetch_fantasy_scores", Mock(side_effect=OSError("offline")))
    response = live_scores.live_response(SimpleNamespace(), 2026, 10, [descriptor()], "espn:123")
    assert response["players"][0]["live_points"] is None
    assert response["players"][0]["pregame_predicted_points"] is None
    assert "unavailable" in response["note"]


def test_private_credentials_separate_live_cache_entries(monkeypatch):
    monkeypatch.setattr(live_scores, "fetch_games", lambda *_: live_scores.parse_games(scoreboard(), 2026, 10))
    provider = Mock(return_value={})
    monkeypatch.setattr(live_scores, "fetch_fantasy_scores", provider)
    for credentials in [("cookie-a", "swid"), ("cookie-b", "swid")]:
        live_scores.live_response(SimpleNamespace(), 2026, 10, [descriptor()], "espn:123", credentials)
    assert provider.call_count == 2


def test_live_routes_allow_negative_defense_ids_and_keep_local_guard(monkeypatch):
    from app.routes import espn
    monkeypatch.setattr(espn, "get_public_league", lambda *_: SimpleNamespace())
    monkeypatch.setattr(live_scores, "fetch_games", lambda *_: {})
    client = TestClient(app)
    request = {"league_id": 123, "season": 2026, "week": 10,
               "players": [{"espn_id": -16002, "player_id": "BUF", "position": "D/ST", "team": "BUF"}]}
    assert client.post('/api/espn/live', json=request).status_code == 200
    monkeypatch.setattr(espn, 'local_espn_api_enabled', lambda: False)
    assert client.post('/api/espn/local/live', json=request).status_code == 404


def test_supported_player_card_method_is_used():
    getter = Mock(return_value=fantasy(4))
    league = SimpleNamespace(espn_request=SimpleNamespace(get_player_card=getter), finalScoringPeriod=18)
    result = live_scores.fetch_fantasy_scores(league, 2026, 10, (501,))
    assert result[501]["points"] == 4
    getter.assert_called_once_with([501], 18)


def test_live_transport_has_timeouts_and_private_credentials_stay_server_side(monkeypatch):
    response = Mock()
    response.json.return_value = fantasy(3)
    request = Mock(return_value=response)
    monkeypatch.setattr(live_scores.requests, "get", request)
    client = live_scores.LiveLeagueClient(123, 2026, 'test-cookie', 'test-swid')
    assert client.get_player_card([-16002, 501], 18) == fantasy(3)
    assert request.call_args.kwargs["timeout"] == (3, 8)
    assert request.call_args.kwargs["cookies"] == {'espn_s2': 'test-cookie', 'SWID': 'test-swid'}
    assert json.loads(request.call_args.kwargs["headers"]["x-fantasy-filter"])["players"]["filterIds"]["value"] == [-16002, 501]


def test_old_history_schema_migrates_without_changing_existing_predictions(monkeypatch):
    import sqlite3
    # Create an old-format row, then remove the new nullable columns to simulate upgrade.
    save(monkeypatch)
    with sqlite3.connect(prediction_history.path) as connection:
        for column in ('floor_points', 'ceiling_points', 'range_note', 'range_revision'):
            connection.execute(f'ALTER TABLE predictions DROP COLUMN {column}')
    row = prediction_history.week_records(2026, 10, 'espn:123')[('QB', 'qb-1')]
    assert row['predicted_points'] == 20
    assert row['floor_points'] is None
    assert row['ceiling_points'] is None
