from types import SimpleNamespace

import pandas as pd

from fastapi.testclient import TestClient

from main import app
from app.routes import espn as espn_route
from app.config.espn_config import ESPNLocalConfig
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
)
from app.services.projection_types import (
    PlayerProjection,
    ProjectionSlateResult,
)

def test_connect_public_league(monkeypatch):
    fake_league = SimpleNamespace(
        current_week=3,
        settings=SimpleNamespace(
            name="Test Fantasy League",
        ),
        teams=[
            SimpleNamespace(
                team_id=1,
                team_name="Toronto Touchdowns",
                team_abbrev="TOR",
                logo_url="https://example.com/logo.png",
            ),
            SimpleNamespace(
                team_id=2,
                team_name="Ottawa Offense",
                team_abbrev="OTT",
                logo_url="",
            ),
        ],
    )

    monkeypatch.setattr(
        espn_route,
        "get_league",
        lambda league_id, year: fake_league,
    )

    client = TestClient(app)

    response = client.post(
        "/api/espn/connect",
        json={
            "league_id": 123456789,
            "season": 2026,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["league_id"] == 123456789
    assert body["season"] == 2026
    assert body["current_week"] == 3
    assert body["league_name"] == "Test Fantasy League"
    assert body["team_count"] == 2
    assert body["teams"][0]["team_name"] == (
        "Toronto Touchdowns"
    )
    assert body["teams"][1]["logo_url"] is None

def test_connect_private_espn_league_returns_403(
    monkeypatch,
):
    def deny_access(league_id, year):
        raise ESPNAccessDenied(
            "espn_s2 and swid are required"
        )

    monkeypatch.setattr(
        espn_route,
        "get_league",
        deny_access,
    )

    client = TestClient(app)

    response = client.post(
        "/api/espn/connect",
        json={
            "league_id": 123456789,
            "season": 2026,
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": (
            "This league is private or ESPN "
            "denied access."
        )
    }


class FakeNFLData:
    def get_week_roster(self, season, week):
        return pd.DataFrame(
            [
                {
                    "player_id": "nfl-1",
                    "player_name": "T.Player",
                    "position": "RB",
                    "team": "ATL",
                }
            ]
        )

    def get_week_opponents(self, season, week):
        return {"ATL": "TB"}

    def get_projection_roster(self, season, week):
        return self.get_week_roster(season, week), week

    def get_player_id_map(self):
        return pd.DataFrame(
            [
                {
                    "espn_id": 501,
                    "player_id": "nfl-1",
                    "position": "RB",
                }
            ]
        )


class FakeESPNProjectionService:
    def __init__(self):
        self.data = FakeNFLData()

    def project_requests(self, position, requests):
        return ProjectionSlateResult(
            projections=[
                PlayerProjection(
                    request=requests[0],
                    position=position,
                    predicted_points=17.25,
                )
            ],
            skipped=[],
        )


def test_public_team_projection_endpoint(monkeypatch):
    fake_league = SimpleNamespace(
        settings=SimpleNamespace(
            name="Test Fantasy League",
        ),
        teams=[
            SimpleNamespace(
                team_id=1,
                team_name="Toronto Touchdowns",
                team_abbrev="TOR",
                logo_url="",
                roster=[
                    SimpleNamespace(
                        playerId=501,
                        name="Test Player",
                        position="RB",
                        lineupSlot="RB",
                    )
                ],
            )
        ],
    )

    monkeypatch.setattr(
        espn_route,
        "get_league",
        lambda league_id, year: fake_league,
    )
    monkeypatch.setattr(
        espn_route,
        "get_espn_projection_service",
        lambda season: FakeESPNProjectionService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/espn/projections",
        json={
            "league_id": 123456789,
            "season": 2024,
            "team_id": 1,
            "week": 1,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["team_id"] == 1
    assert body["roster_week"] == 1
    assert body["projected_count"] == 1
    assert body["skipped_count"] == 0
    assert body["players"][0] == {
        "espn_id": 501,
        "player_id": "nfl-1",
        "player_name": "Test Player",
        "position": "RB",
        "lineup_slot": "RB",
        "team": "ATL",
        "opponent_team": "TB",
        "predicted_points": 17.25,
        "status": "projected",
        "reason": None,
    }


def make_private_league():
    return SimpleNamespace(
        settings=SimpleNamespace(
            name="Private Test League",
        ),
        teams=[
            SimpleNamespace(
                team_id=1,
                team_name="Private Team",
                team_abbrev="PRV",
                logo_url="",
                roster=[
                    SimpleNamespace(
                        playerId=501,
                        name="Test Player",
                        position="RB",
                        lineupSlot="RB",
                    )
                ],
            )
        ],
    )


def configure_private_route(monkeypatch):
    monkeypatch.setattr(
        espn_route,
        "local_espn_api_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        espn_route,
        "get_local_espn_config",
        lambda: ESPNLocalConfig(
            league_id=987654321,
            season=2024,
            swid="private-swid",
            espn_s2="private-espn-s2",
        ),
    )

    def fake_get_league(
        league_id,
        year,
        espn_s2,
        swid,
    ):
        assert league_id == 987654321
        assert year == 2024
        assert espn_s2 == "private-espn-s2"
        assert swid == "private-swid"
        return make_private_league()

    monkeypatch.setattr(
        espn_route,
        "get_league",
        fake_get_league,
    )


def test_local_private_league_connection(monkeypatch):
    configure_private_route(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/api/espn/local/connect"
    )

    assert response.status_code == 200
    assert response.json()["league_name"] == (
        "Private Test League"
    )
    assert "private-swid" not in response.text
    assert "private-espn-s2" not in response.text


def test_local_private_league_projections(monkeypatch):
    configure_private_route(monkeypatch)
    monkeypatch.setattr(
        espn_route,
        "get_espn_projection_service",
        lambda season: FakeESPNProjectionService(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/espn/local/projections",
        json={
            "team_id": 1,
            "week": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["league_id"] == 987654321
    assert body["projected_count"] == 1
    assert body["players"][0]["predicted_points"] == 17.25


def test_local_private_route_is_hidden_when_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        espn_route,
        "local_espn_api_enabled",
        lambda: False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/espn/local/connect"
    )

    assert response.status_code == 404


def test_projection_keeps_unsupported_roster_players(
    monkeypatch,
):
    fake_league = make_private_league()
    fake_league.teams[0].roster.append(
        SimpleNamespace(
            playerId=999,
            name="Test Kicker",
            position="K",
            lineupSlot="K",
        )
    )

    monkeypatch.setattr(
        espn_route,
        "get_public_league",
        lambda league_id, season: fake_league,
    )
    monkeypatch.setattr(
        espn_route,
        "get_espn_projection_service",
        lambda season: FakeESPNProjectionService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/espn/projections",
        json={
            "league_id": 123,
            "season": 2024,
            "team_id": 1,
            "week": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["players"]) == 2
    kicker = body["players"][1]
    assert kicker["player_name"] == "Test Kicker"
    assert kicker["status"] == "skipped"
    assert kicker["reason"] == (
        "AI projections are not supported for K yet."
    )
