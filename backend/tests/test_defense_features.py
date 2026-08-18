import pandas as pd

from app.config.model_config import (
    DEFENSE_STAT_COLS,
)
from app.services.defense_features import (
    build_pregame_defense_features,
)


def test_pregame_defense_features_exclude_current_week():
    rows = []

    for week, value in [
        (1, 10.0),
        (2, 20.0),
        (3, 30.0),
    ]:
        row = {
            "opponent_team": "BUF",
            "season": 2024,
            "position": "QB",
            "week": week,
        }

        row.update(
            {
                column: value
                for column in DEFENSE_STAT_COLS
            }
        )

        rows.append(row)

    defense_df = pd.DataFrame(rows)

    result = build_pregame_defense_features(
        defense_df
    )

    values = result[
        "fantasy_points_ppr_allowed"
    ].tolist()

    assert values == [0.0, 10.0, 15.0]