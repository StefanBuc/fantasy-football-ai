from typing import Any
import torch
import pandas as pd
from sklearn.preprocessing import StandardScaler
from bisect import bisect_left
import numpy as np

from app.services.defense_features import (
    build_upcoming_defense_features,
)

from app.services.player_sequence_dataset import (
    build_player_history,
    prepare_player_history_features
)

from app.services.pytorch_projection_model import (
    load_selected_projection_checkpoint,
    predict_batch_from_raw_features,
    predict_from_raw_features,
)

from app.services.projection_types import (
    PlayerProjectionRequest,
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
    prepared_player_df: pd.DataFrame | None = None,
    prepared_matchup: dict[str, float] | None = None,
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
        prepared_player_df=prepared_player_df,
    )

    if prepared_matchup is None:
        matchup = build_upcoming_defense_features(
            defense_df=defense_df,
            defense_team=opponent_team,
            season=season,
            position=position,
            upcoming_week=upcoming_week,
        )
    else:
        matchup = prepared_matchup

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
        player_df: pd.DataFrame,
        defense_df: pd.DataFrame,
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
        self.matchup_cache: dict[tuple[str, int, int], dict[str, float]] = {}
        
        position_player_df = player_df[
            player_df["position"] == self.position
        ].copy()

        self.defense_df = defense_df[
            defense_df["position"] == self.position
        ].copy()

        self.prepared_player_df = (
            prepare_player_history_features(
                position_player_df,
                self.defense_df,
            )
        )
        
        feature_cols = self.checkpoint["feature_cols"]

        cleaned_history_df = self.prepared_player_df.copy()

        cleaned_history_df[feature_cols] = (
            cleaned_history_df[feature_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(float)
        )

        self.player_history_by_id: dict[
            str,
            tuple[
                list[tuple[int, int]],
                list[dict[str, float]],
            ],
        ] = {}

        for player_id, history_df in (
            cleaned_history_df.groupby(
                "player_id",
                sort=False,
            )
        ):
            history_df = history_df.sort_values(
                ["season", "week"]
            )

            game_keys = [
                (int(season), int(week))
                for season, week in zip(
                    history_df["season"],
                    history_df["week"],
                )
            ]

            feature_values = history_df[
                feature_cols
            ].to_numpy(dtype=np.float32)

            history_records = [
                {
                    column: float(value)
                    for column, value in zip(
                        feature_cols,
                        row,
                    )
                }
                for row in feature_values
            ]

            self.player_history_by_id[str(player_id)] = (
                game_keys,
                history_records,
            )

    def predict(
        self,
        player_id: str,
        season: int,
        upcoming_week: int,
        opponent_team: str,
    ) -> float:
        
        request = PlayerProjectionRequest(
            player_id=player_id,
            season=season,
            upcoming_week=upcoming_week,
            opponent_team=opponent_team,
        )

        return self.predict_many([request])[0]
    
    def _get_history(
        self,
        player_id: str,
        season: int,
        upcoming_week: int,
    ) -> list[dict[str, float]]:
        if player_id not in self.player_history_by_id:
            return []
        
        game_keys, history_records = self.player_history_by_id[player_id]
        
        sequence_length = self.checkpoint["sequence_length"]
        
        # Find the index of the latest game before upcoming_week
        target_week_index = bisect_left(
            game_keys,
            (season, upcoming_week),
        )
        
        # Get the most recent sequence_length records up to the target week
        start_index = max(0, target_week_index - sequence_length)
        end_index = target_week_index
        
        return history_records[start_index:end_index]
    
    def _get_matchup(
        self,
        opponent_team: str,
        season: int,
        upcoming_week: int,
    ) -> dict[str, float]:
        normalized_opponent = opponent_team.upper()

        matchup_key = (
            normalized_opponent,
            season,
            upcoming_week,
        )

        if matchup_key not in self.matchup_cache:
            self.matchup_cache[matchup_key] = (
                build_upcoming_defense_features(
                    defense_df=self.defense_df,
                    defense_team=normalized_opponent,
                    season=season,
                    position=self.position,
                    upcoming_week=upcoming_week,
                )
            )

        return self.matchup_cache[matchup_key]

    def predict_many(
        self,
        requests: list[PlayerProjectionRequest],
    ) -> list[float]:
        histories = []
        matchups = []

        for request in requests:
            
            history = self._get_history(
                player_id=request.player_id,
                season=request.season,
                upcoming_week=request.upcoming_week,
            )

            matchup = self._get_matchup(
                opponent_team=request.opponent_team,
                season=request.season,
                upcoming_week=request.upcoming_week,
            )

            histories.append(history)
            matchups.append(matchup)

        return predict_batch_from_raw_features(
            model=self.model,
            sequence_scaler=self.sequence_scaler,
            matchup_scaler=self.matchup_scaler,
            checkpoint=self.checkpoint,
            device=self.device,
            histories=histories,
            matchups=matchups,
        )
    
    def history_games_available(
        self,
        request: PlayerProjectionRequest,
    ) -> int:
        stored_history = self.player_history_by_id.get(
            request.player_id
        )

        if stored_history is None:
            return 0

        game_keys, _ = stored_history

        return bisect_left(
            game_keys,
            (
                request.season,
                request.upcoming_week,
            ),
        )


    def can_predict(
        self,
        request: PlayerProjectionRequest,
    ) -> bool:
        available_games = (
            self.history_games_available(request)
        )

        return (
            available_games
            >= self.checkpoint["sequence_length"]
        )