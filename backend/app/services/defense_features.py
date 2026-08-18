import pandas as pd
import numpy as np
from pathlib import Path
from app.config.model_config import DEFENSE_STAT_COLS

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def build_upcoming_defense_features(
    defense_df: pd.DataFrame,
    defense_team: str,
    season: int,
    position: str,
    upcoming_week: int,
) -> dict[str, float]:
    '''
    Build defense features for a specific team, season, position, and upcoming week.
    '''
    
    previous_games = defense_df[
        (defense_df["opponent_team"] == defense_team)
        & (defense_df["season"] == season)
        & (defense_df["position"] == position)
        & (defense_df["week"] < upcoming_week)
    ]

    if previous_games.empty:
        return {col: 0.0 for col in DEFENSE_STAT_COLS}

    averages = (
        previous_games[DEFENSE_STAT_COLS]
        .replace([np.inf, -np.inf], np.nan)
        .mean()
        .fillna(0.0)
    )

    return {
        column: float(averages[column])
        for column in DEFENSE_STAT_COLS
    }

def build_pregame_defense_features(
    defense_df: pd.DataFrame,
) -> pd.DataFrame:
    '''
    Build pregame defense features for all teams, seasons, positions, and weeks.
    '''
    defense_df = defense_df.copy()

    defense_df = defense_df.sort_values(
        [
            "opponent_team",
            "season",
            "position",
            "week",
        ]
    ).reset_index(drop=True)

    defense_df[DEFENSE_STAT_COLS] = (
        defense_df
        .groupby(
            [
                "opponent_team",
                "season",
                "position",
            ]
        )[DEFENSE_STAT_COLS]
        .transform(
            lambda group: (
                group.shift(1)
                .expanding()
                .mean()
            )
        )
    )

    defense_df[DEFENSE_STAT_COLS] = (
        defense_df[DEFENSE_STAT_COLS].fillna(0)
    )

    return defense_df