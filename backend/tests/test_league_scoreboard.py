import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from main import app
from app.routes import espn


def league_with_scores():
    request = Mock(return_value={"schedule": [{
        "matchupPeriodId": 10,
        "home": {"teamId": 1, "totalPoints": 0, "totalPointsLive": 125.2},
        "away": {"teamId": 2, "totalPoints": 0, "totalPointsLive": 141.2},
    }]})
    return SimpleNamespace(
        teams=[SimpleNamespace(team_id=1, team_name="Home"),
               SimpleNamespace(team_id=2, team_name="Away")],
        settings=SimpleNamespace(matchup_periods={"10": [10]}),
        espn_request=SimpleNamespace(league_get=request),
    )


def test_scoreboard_uses_live_totals_not_zero_summary():
    league = league_with_scores()
    result = espn.build_scoreboard_response(league, 10)
    assert result.opponents_by_team == {1: 2, 2: 1}
    assert result.scoreboard[0].home_score == 125.2
    assert result.scoreboard[0].away_score == 141.2
    assert league.espn_request.league_get.call_args.kwargs["params"]["scoringPeriodId"] == 10


def test_multiweek_matchups_use_requested_week_and_missing_is_not_zero():
    league = league_with_scores()
    league.settings.matchup_periods = {"5": [10, 11]}
    league.espn_request.league_get.return_value = {"schedule": [{
        "matchupPeriodId": 5,
        "home": {"teamId": 1, "totalPoints": 200, "pointsByScoringPeriod": {"10": 99.5}},
        "away": {"teamId": 2, "totalPoints": 220},
    }, {"matchupPeriodId": 6, "home": {"teamId": 1}, "away": {"teamId": 2}}]}
    result = espn.build_scoreboard_response(league, 10)
    assert len(result.scoreboard) == 1
    assert result.scoreboard[0].home_score == 99.5
    assert result.scoreboard[0].away_score is None
    filters = json.loads(league.espn_request.league_get.call_args.kwargs["headers"]["x-fantasy-filter"])
    assert filters["schedule"]["filterMatchupPeriodIds"]["value"] == [5]


@pytest.mark.parametrize("path", ["/api/espn/scoreboard", "/api/espn/local/scoreboard"])
def test_scoreboard_stays_available_across_refresh_without_model_inference(monkeypatch, path):
    league = league_with_scores()
    monkeypatch.setattr(espn, "get_public_league", lambda *args: league)
    monkeypatch.setattr(espn, "get_configured_private_league", lambda request: (None, league))
    model = Mock(side_effect=AssertionError("Scoreboard must not run inference"))
    monkeypatch.setattr(espn, "get_espn_projection_service", model)
    client = TestClient(app)
    body = {"league_id": 123, "season": 2026, "week": 10}
    for _ in range(2):
        response = client.post(path, json=body)
        assert response.status_code == 200
        assert response.json()["opponents_by_team"] == {"1": 2, "2": 1}
        assert response.json()["scoreboard"][0]["home_score"] == 125.2
    model.assert_not_called()
