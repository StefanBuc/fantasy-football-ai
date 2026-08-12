from typing import Any
import torch
import pandas as pd
from sklearn.preprocessing import StandardScaler

from app.services.defense_features import (
    build_upcoming_defense_features,
)

from app.services.player_sequence_dataset import (
    build_player_history,
)

from app.services.pytorch_projection_model import (
    predict_from_raw_features,
    load_selected_projection_checkpoint,
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
    
class PyTorchProjectionService:
    def __init__(
        self,
        position: str,
        device: torch.device | None = None,
    ):
        (
            self.model,
            self.sequence_scaler,
            self.matchup_scaler,
            self.checkpoint,
            self.device,
        ) = load_selected_projection_checkpoint(
            position=position,
            device=device,
        )

        self.position = self.checkpoint["position"]

    def predict(
        self,
        player_df: pd.DataFrame,
        defense_df: pd.DataFrame,
        player_id: str,
        season: int,
        upcoming_week: int,
        opponent_team: str,
    ) -> float:
        return predict_player_projection(
            model=self.model,
            sequence_scaler=self.sequence_scaler,
            matchup_scaler=self.matchup_scaler,
            checkpoint=self.checkpoint,
            device=self.device,
            player_df=player_df,
            defense_df=defense_df,
            player_id=player_id,
            season=season,
            upcoming_week=upcoming_week,
            opponent_team=opponent_team,
        )