import pandas as pd

from app.services.special_teams_data import (
    build_dst_weekly,
    build_kicker_weekly,
    score_dst_week,
    score_kicker_week,
)


def test_scores_kicker_using_espn_distance_bands():
    assert score_kicker_week(
        field_goals_0_39=1,
        field_goals_40_49=1,
        field_goals_50_59=1,
        field_goals_60_plus=1,
        field_goals_missed=1,
        extra_points_made=2,
    ) == 19


def test_builds_kicker_week_from_play_by_play():
    plays = pd.DataFrame(
        [
            {
                "season": 2024,
                "season_type": "REG",
                "week": 1,
                "play_type": "field_goal",
                "kicker_player_id": "kicker-1",
                "kicker_player_name": "K. Icker",
                "posteam": "BUF",
                "defteam": "MIA",
                "field_goal_result": "made",
                "extra_point_result": None,
                "kick_distance": 52,
            },
            {
                "season": 2024,
                "season_type": "REG",
                "week": 1,
                "play_type": "extra_point",
                "kicker_player_id": "kicker-1",
                "kicker_player_name": "K. Icker",
                "posteam": "BUF",
                "defteam": "MIA",
                "field_goal_result": None,
                "extra_point_result": "good",
                "kick_distance": 33,
            },
        ]
    )

    result = build_kicker_weekly(plays)

    assert len(result) == 1
    assert result.loc[0, "field_goals_50_59"] == 1
    assert result.loc[0, "extra_points_made"] == 1
    assert result.loc[0, "fantasy_points"] == 6


def test_scores_dst_using_espn_points_and_yards_bands():
    assert score_dst_week(
        sacks=3,
        interceptions=1,
        fumble_recoveries=1,
        blocked_kicks=0,
        safeties=0,
        return_touchdowns=1,
        points_allowed=10,
        yards_allowed=250,
    ) == 18


def test_builds_two_dst_rows_for_a_game():
    base = {
        "game_id": "game-1",
        "season": 2024,
        "season_type": "REG",
        "week": 1,
        "home_team": "BUF",
        "away_team": "MIA",
        "touchdown": 0,
        "td_team": None,
        "fumble_lost": 0,
        "safety": 0,
        "return_touchdown": 0,
        "extra_point_result": None,
        "field_goal_result": None,
        "kick_distance": None,
        "kicker_player_id": None,
        "kicker_player_name": None,
        "punt_blocked": 0,
    }
    plays = pd.DataFrame(
        [
            {
                **base,
                "posteam": "MIA",
                "defteam": "BUF",
                "play_type": "pass",
                "interception": 1,
                "sack": 0,
                "yards_gained": 20,
                "total_home_score": 7,
                "total_away_score": 0,
            },
            {
                **base,
                "posteam": "BUF",
                "defteam": "MIA",
                "play_type": "run",
                "interception": 0,
                "sack": 0,
                "yards_gained": 30,
                "total_home_score": 10,
                "total_away_score": 3,
            },
        ]
    )

    result = build_dst_weekly(plays)

    assert set(result["entity_id"]) == {"BUF", "MIA"}
    buffalo = result[result["entity_id"] == "BUF"].iloc[0]
    assert buffalo["interceptions"] == 1
    assert buffalo["points_allowed"] == 3
    assert buffalo["yards_allowed"] == 20
