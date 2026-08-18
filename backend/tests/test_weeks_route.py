import pandas as pd
from fastapi.testclient import TestClient

from main import app
from app.routes import weeks as weeks_route


class FakeScheduleData:
    def __init__(self):
        self.schedule = pd.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "away_team": "BAL",
                    "home_team": "KC",
                },
                {
                    "season": 2024,
                    "week": 1,
                    "away_team": "ARI",
                    "home_team": "BUF",
                },
                {
                    "season": 2024,
                    "week": 2,
                    "away_team": "BUF",
                    "home_team": "MIA",
                },
            ]
        )

    def get_week_schedule(
        self,
        season: int,
        week: int,
    ) -> pd.DataFrame:
        return self.schedule[
            (self.schedule["season"] == season)
            & (self.schedule["week"] == week)
        ].copy()


def test_get_weeks_by_season(monkeypatch):
    monkeypatch.setattr(
        weeks_route,
        "get_schedule_data",
        lambda season: FakeScheduleData(),
    )

    client = TestClient(app)
    response = client.get("/api/weeks/2024")

    assert response.status_code == 200

    body = response.json()

    assert body["season"] == 2024
    assert body["count"] == 2
    assert body["weeks"] == [
        {"week": 1, "game_count": 2},
        {"week": 2, "game_count": 1},
    ]


def test_get_specific_week_schedule(monkeypatch):
    monkeypatch.setattr(
        weeks_route,
        "get_schedule_data",
        lambda season: FakeScheduleData(),
    )

    client = TestClient(app)
    response = client.get("/api/weeks/2024/1")

    assert response.status_code == 200

    body = response.json()

    assert body["game_count"] == 2
    assert body["games"][0] == {
        "away_team": "BAL",
        "home_team": "KC",
    }