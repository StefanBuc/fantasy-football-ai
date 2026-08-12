from typing import Any

import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

from app.services.defense_features import (
    build_upcoming_defense_features,
)

from app.services.player_sequence_dataset import (
    build_player_history,
)

from app.services.pytorch_projection_model import (
    predict_from_raw_features,
)

def predict_player_projection(
    model: torch.nn.Module,
    sequence_scaler: StandardScaler,
    matchup_scaler: StandardScaler,
    checkpoint: dict[str, Any],
    device: torch.device,
    player_df: pd.DataFrame,
    defense_df: pd.DataFrame,
    player_id: str,
    season: int,
    upcoming_week: int,
    opponent_team: str,
) -> float:
    position = checkpoint["position"]

    history = build_player_history(
        player_df=player_df,
        defense_df=defense_df,
        player_id=player_id,
        season=season,
        upcoming_week=upcoming_week,
        position=position,
        feature_cols=checkpoint["feature_cols"],
        sequence_length=checkpoint["sequence_length"],
    )

    matchup = build_upcoming_defense_features(
        defense_df=defense_df,
        defense_team=opponent_team,
        season=season,
        position=position,
        upcoming_week=upcoming_week,
    )

    return predict_from_raw_features(
        model=model,
        sequence_scaler=sequence_scaler,
        matchup_scaler=matchup_scaler,
        checkpoint=checkpoint,
        device=device,
        history=history,
        matchup=matchup,
    )