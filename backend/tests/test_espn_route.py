from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from app.routes import espn as espn_route
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
)

def test_connect_public_league(monkeypatch):
    fake_league = SimpleNamespace(
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