import pandas as pd

from app.services.projection_types import PlayerProjectionRequest
from app.services.pytorch_inference import PyTorchProjectionService


def make_service() -> PyTorchProjectionService:
    service = object.__new__(PyTorchProjectionService)
    service.checkpoint = {"sequence_length": 5}
    service.player_history_by_id = {
        "limited": (
            [(2024, 1), (2024, 2)],
            [
                {"fantasy_points_ppr": 10.0},
                {"fantasy_points_ppr": 14.0},
            ],
        )
    }
    service.prepared_player_df = pd.DataFrame(
        [
            {
                "season": 2023,
                "week": 18,
                "fantasy_points_ppr": 6.0,
            },
            {
                "season": 2024,
                "week": 1,
                "fantasy_points_ppr": 10.0,
            },
            {
                "season": 2024,
                "week": 3,
                "fantasy_points_ppr": 100.0,
            },
        ]
    )
    return service


def make_request(player_id: str) -> PlayerProjectionRequest:
    return PlayerProjectionRequest(
        player_id=player_id,
        season=2024,
        upcoming_week=3,
        opponent_team="MIA",
    )


def test_limited_history_uses_available_game_average():
    result = make_service().predict_cold_start(
        make_request("limited")
    )

    assert result == (12.0, "recent_average")


def test_no_history_uses_prior_position_average_only():
    result = make_service().predict_cold_start(
        make_request("rookie")
    )

    assert result == (8.0, "position_average")


def test_matchup_contains_live_teammate_context():
    service = make_service()
    service.position = "QB"
    service.matchup_cache = {
        ("MIA", 2024, 3): {
            "passing_yards_allowed": 200.0,
        }
    }
    request = PlayerProjectionRequest(
        player_id="limited",
        season=2024,
        upcoming_week=3,
        opponent_team="MIA",
        teammate_out_count=1.0,
        teammate_out_target_share=0.25,
        teammate_out_carries=7.0,
        teammate_out_offense_pct=0.8,
    )

    matchup = service._get_matchup(request)

    assert matchup["passing_yards_allowed"] == 200.0
    assert matchup["teammate_out_count"] == 1.0
    assert matchup["teammate_out_target_share"] == 0.25
    assert matchup["teammate_out_carries"] == 7.0
    assert matchup["teammate_out_offense_pct"] == 0.8
