import pandas as pd

from app.services.special_teams_sequence_dataset import (
    SpecialTeamsSequenceDataset,
    build_special_teams_matchup,
)


def make_weekly_rows():
    rows = []
    for week in range(1, 8):
        rows.append(
            {
                "entity_id": "kicker-1",
                "entity_name": "Test Kicker",
                "team": "BUF",
                "opponent_team": "MIA",
                "season": 2024,
                "week": week,
                "fantasy_points": float(week),
                "field_goals_attempted": 1.0,
                "extra_points_attempted": 2.0,
            }
        )
    return pd.DataFrame(rows)


def test_matchup_excludes_target_week():
    result = build_special_teams_matchup(
        weekly_df=make_weekly_rows(),
        opponent_team="MIA",
        season=2024,
        week=4,
        matchup_sources={
            "points_allowed": "fantasy_points",
        },
    )

    assert result["points_allowed"] == 2.0


def test_special_teams_dataset_builds_sequences():
    dataset = SpecialTeamsSequenceDataset(
        weekly_df=make_weekly_rows(),
        feature_cols=[
            "fantasy_points",
            "field_goals_attempted",
            "extra_points_attempted",
            "week",
        ],
        matchup_sources={
            "points_allowed": "fantasy_points",
        },
        sequence_length=5,
        seasons=[2024],
        target_seasons=[2024],
    )

    assert len(dataset) == 2
    sequence, matchup, target = dataset[0]
    assert sequence.shape == (5, 4)
    assert matchup.shape == (1,)
    assert target.item() == 6.0
