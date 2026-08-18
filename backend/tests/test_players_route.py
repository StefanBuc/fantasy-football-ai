import pandas as pd
from fastapi.testclient import TestClient

from main import app
from app.routes import players as players_route


class FakeNFLData:
    def get_player_stats(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "player_id": "00-test-player",
                    "player_name": "Test Player",
                    "position": "QB",
                    "recent_team": "BUF",
                    "season": 2023,
                    "week": 18,
                    "fantasy_points_ppr": 15.0,
                    "receiving_yards": float("nan"),
                },
                {
                    "player_id": "00-test-player",
                    "player_name": "Test Player",
                    "position": "QB",
                    "recent_team": "BUF",
                    "season": 2024,
                    "week": 1,
                    "fantasy_points_ppr": 20.0,
                    "receiving_yards": float("nan"),
                },
            ]
        )


def test_player_summary_and_stats(monkeypatch):
    monkeypatch.setattr(
        players_route,
        "get_nfl_data",
        lambda: FakeNFLData(),
    )

    client = TestClient(app)

    summary_response = client.get(
        "/api/players/00-test-player"
    )

    assert summary_response.status_code == 200
    assert summary_response.json()["player"] == {
        "player_id": "00-test-player",
        "player_name": "Test Player",
        "position": "QB",
        "team": "BUF",
    }

    stats_response = client.get(
        "/api/players/00-test-player/stats"
    )

    assert stats_response.status_code == 200

    stats = stats_response.json()["player_stats"]

    assert len(stats) == 2
    assert stats[0]["season"] == 2023
    assert stats[1]["season"] == 2024
    assert stats[1]["fantasy_points_ppr"] == 20.0
    assert stats[1]["receiving_yards"] is None