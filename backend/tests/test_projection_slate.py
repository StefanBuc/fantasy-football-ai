import pandas as pd

from app.services.projection_slate import (
    build_projection_requests,
    project_position_slate,
)
from app.services.projection_types import (
    PlayerProjectionRequest,
)

def test_build_projection_requests_assigns_opponent():
    roster = pd.DataFrame(
        [
            {
                "player_id": "player-1",
                "player_name": "Test Quarterback",
                "position": "QB",
                "team": "BUF",
                "season": 2024,
                "week": 1,
            }
        ]
    )

    opponents = {
        "BUF": "ARI",
        "ARI": "BUF",
    }

    requests = build_projection_requests(
        roster_df=roster,
        opponents=opponents,
        position="QB",
    )

    assert len(requests) == 1
    assert requests[0].player_id == "player-1"
    assert requests[0].opponent_team == "ARI"
    
def test_build_projection_requests_keeps_only_top_active_qb():
    roster = pd.DataFrame(
        [
            {
                "player_id": "qb-1",
                "player_name": "Starting QB",
                "position": "QB",
                "team": "BUF",
                "season": 2024,
                "week": 1,
            },
            {
                "player_id": "qb-2",
                "player_name": "Backup QB",
                "position": "QB",
                "team": "BUF",
                "season": 2024,
                "week": 1,
            },
        ]
    )

    depth_chart = pd.DataFrame(
        [
            {
                "player_id": "qb-1",
                "team": "BUF",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": 1,
            },
            {
                "player_id": "qb-2",
                "team": "BUF",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": 2,
            },
        ]
    )

    requests = build_projection_requests(
        roster_df=roster,
        opponents={"BUF": "ARI"},
        position="QB",
        depth_chart_df=depth_chart,
    )

    assert len(requests) == 1
    assert requests[0].player_id == "qb-1"
    assert requests[0].depth_team == 1
    assert requests[0].active_depth_rank == 1
    
def test_build_projection_requests_promotes_active_backup():
    roster = pd.DataFrame(
        [
            {
                "player_id": "qb-2",
                "player_name": "Active Backup",
                "position": "QB",
                "team": "BUF",
                "season": 2024,
                "week": 1,
            }
        ]
    )

    depth_chart = pd.DataFrame(
        [
            {
                "player_id": "qb-1",
                "team": "BUF",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": 1,
            },
            {
                "player_id": "qb-2",
                "team": "BUF",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": 2,
            },
        ]
    )

    requests = build_projection_requests(
        roster_df=roster,
        opponents={"BUF": "ARI"},
        position="QB",
        depth_chart_df=depth_chart,
    )

    assert len(requests) == 1
    assert requests[0].player_id == "qb-2"
    assert requests[0].depth_team == 2
    assert requests[0].active_depth_rank == 1


class FakeColdStartService:
    position = "QB"
    checkpoint = {"sequence_length": 5}

    def history_games_available(self, request):
        return {
            "established": 5,
            "limited": 2,
            "rookie": 0,
        }[request.player_id]

    def predict_many(self, requests):
        assert [request.player_id for request in requests] == [
            "established"
        ]
        return [20.0]

    def predict_cold_start(self, request):
        if request.player_id == "limited":
            return 12.0, "recent_average"
        if request.player_id == "rookie":
            return 8.0, "position_average"
        return None


def test_projection_slate_labels_cold_start_fallbacks():
    requests = [
        PlayerProjectionRequest(
            player_id=player_id,
            player_name=player_id.title(),
            team="BUF",
            season=2024,
            upcoming_week=3,
            opponent_team="MIA",
        )
        for player_id in [
            "established",
            "limited",
            "rookie",
        ]
    ]

    result = project_position_slate(
        service=FakeColdStartService(),
        requests=requests,
    )

    by_player = {
        projection.request.player_id: projection
        for projection in result.projections
    }

    assert not result.skipped
    assert by_player["established"].projection_method == "model"
    assert by_player["established"].history_games == 5
    assert by_player["limited"].predicted_points == 12.0
    assert by_player["limited"].projection_method == "recent_average"
    assert by_player["limited"].history_games == 2
    assert by_player["rookie"].predicted_points == 8.0
    assert by_player["rookie"].projection_method == "position_average"
    assert by_player["rookie"].history_games == 0
