import pandas as pd

from app.services.projection_slate import (
    build_projection_requests,
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