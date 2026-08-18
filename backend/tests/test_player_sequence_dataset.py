import pandas as pd
import pytest

from app.services.player_sequence_dataset import (
    build_player_history,
)


def test_build_player_history_excludes_target_week():
    prepared_players = pd.DataFrame(
        [
            {
                "player_id": "qb-1",
                "position": "QB",
                "season": 2024,
                "week": week,
                "fantasy_points_ppr": points,
            }
            for week, points in [
                (1, 1.0),
                (2, 2.0),
                (3, 3.0),
                (4, 4.0),
                (5, 5.0),
                (6, 99.0),
            ]
        ]
    )

    history = build_player_history(
        player_df=pd.DataFrame(),
        defense_df=pd.DataFrame(),
        player_id="qb-1",
        season=2024,
        upcoming_week=6,
        position="QB",
        feature_cols=["fantasy_points_ppr"],
        sequence_length=5,
        prepared_player_df=prepared_players,
    )

    points = [
        game["fantasy_points_ppr"]
        for game in history
    ]

    assert points == [1.0, 2.0, 3.0, 4.0, 5.0]
    
def test_build_player_history_uses_previous_season():
    prepared_players = pd.DataFrame(
        [
            {
                "player_id": "qb-1",
                "position": "QB",
                "season": 2023,
                "week": week,
                "fantasy_points_ppr": float(week),
            }
            for week in [14, 15, 16, 17, 18]
        ]
        + [
            {
                "player_id": "qb-1",
                "position": "QB",
                "season": 2024,
                "week": 1,
                "fantasy_points_ppr": 99.0,
            }
        ]
    )

    history = build_player_history(
        player_df=pd.DataFrame(),
        defense_df=pd.DataFrame(),
        player_id="qb-1",
        season=2024,
        upcoming_week=1,
        position="QB",
        feature_cols=["fantasy_points_ppr"],
        sequence_length=5,
        prepared_player_df=prepared_players,
    )

    points = [
        game["fantasy_points_ppr"]
        for game in history
    ]

    assert points == [14.0, 15.0, 16.0, 17.0, 18.0]
    
def test_build_player_history_rejects_insufficient_games():
    prepared_players = pd.DataFrame(
        [
            {
                "player_id": "rookie-1",
                "position": "QB",
                "season": 2024,
                "week": week,
                "fantasy_points_ppr": float(week),
            }
            for week in [1, 2, 3, 4]
        ]
    )

    with pytest.raises(
        ValueError,
        match="only 4 games",
    ):
        build_player_history(
            player_df=pd.DataFrame(),
            defense_df=pd.DataFrame(),
            player_id="rookie-1",
            season=2024,
            upcoming_week=5,
            position="QB",
            feature_cols=["fantasy_points_ppr"],
            sequence_length=5,
            prepared_player_df=prepared_players,
        )