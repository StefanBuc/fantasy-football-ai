import pandas as pd
import pytest

from app.services.teammate_injury_features import (
    build_historical_team_injury_context,
    build_live_team_injury_context,
)


def player_history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": "out-player",
                "season": 2024,
                "season_type": "REG",
                "week": 1,
                "target_share": 0.10,
                "carries": 4.0,
                "offense_pct": 0.60,
            },
            {
                "player_id": "out-player",
                "season": 2024,
                "season_type": "REG",
                "week": 2,
                "target_share": 0.20,
                "carries": 8.0,
                "offense_pct": 0.80,
            },
            {
                "player_id": "out-player",
                "season": 2024,
                "season_type": "REG",
                "week": 3,
                "target_share": 1.0,
                "carries": 100.0,
                "offense_pct": 1.0,
            },
        ]
    )


def test_live_context_uses_only_games_before_target_week():
    context = build_live_team_injury_context(
        player_df=player_history(),
        unavailable_players=[
            {
                "player_id": "out-player",
                "team": "BUF",
            }
        ],
        season=2024,
        week=3,
    )["BUF"]

    assert context["teammate_out_count"] == 1.0
    assert context["teammate_out_target_share"] == pytest.approx(0.15)
    assert context["teammate_out_carries"] == 6.0
    assert context["teammate_out_offense_pct"] == pytest.approx(0.7)


def test_historical_context_uses_latest_weekly_report():
    injuries = pd.DataFrame(
        [
            {
                "season": 2024,
                "game_type": "REG",
                "team": "BUF",
                "week": 3,
                "gsis_id": "out-player",
                "position": "WR",
                "report_status": "Questionable",
                "date_modified": "2024-09-10 10:00:00",
            },
            {
                "season": 2024,
                "game_type": "REG",
                "team": "BUF",
                "week": 3,
                "gsis_id": "out-player",
                "position": "WR",
                "report_status": "Out",
                "date_modified": "2024-09-12 10:00:00",
            },
            {
                "season": 2024,
                "game_type": "REG",
                "team": "BUF",
                "week": 3,
                "gsis_id": "defender",
                "position": "CB",
                "report_status": "Out",
                "date_modified": "2024-09-12 10:00:00",
            },
        ]
    )

    result = build_historical_team_injury_context(
        player_df=player_history(),
        injury_df=injuries,
    )

    assert len(result) == 1
    row = result.iloc[0]
    assert row["recent_team"] == "BUF"
    assert row["teammate_out_count"] == 1.0
    assert row["teammate_out_target_share"] == pytest.approx(0.15)
    assert row["teammate_out_carries"] == 6.0
