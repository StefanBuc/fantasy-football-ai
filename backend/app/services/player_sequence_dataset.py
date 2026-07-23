import numpy as np
import pandas as pd
from pathlib import Path
import torch
from torch.utils.data import Dataset
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent.parent.parent

PLAYER_COLS = [
    "player_id",
    "player_name",
    "position",
    "recent_team",
    "opponent_team",
    "season",
    "week",
    "fantasy_points_ppr",
    "targets",
    "receptions",
    "carries",
    "passing_yards",
    "passing_tds",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "target_share",
    "wopr",
    "offense_pct",
]

DEFENSE_COLS = [
    "opponent_team",
    "season",
    "week",
    "position",
    "passing_yards_allowed",
    "rushing_yards_allowed",
    "receiving_yards_allowed",
    "passing_tds_allowed",
    "rushing_tds_allowed",
    "receiving_tds_allowed",
    "fantasy_points_ppr_allowed",
    "targets_allowed",
    "receptions_allowed",
]

class PlayerSequenceDataset(Dataset):
    def __init__(self, player_df: pd.DataFrame, defense_df: pd.DataFrame, feature_cols: list, sequence_length: int = 5, position: str | None = None, seasons: list[int] | None = None, scaler: StandardScaler | None = None):
        self.position = position
        self.feature_cols = feature_cols
        self.sequence_length = sequence_length
        self.sequences: list[np.ndarray] = []
        self.targets: list[float] = []
        self.scaler = scaler
        
        player_df = player_df.copy()
        
        if seasons is not None:
            player_df = player_df[player_df["season"].isin(seasons)]
            defense_df = defense_df[defense_df["season"].isin(seasons)]

        if position is not None:
            player_df = player_df[
                (player_df["position"] == position)
                & (player_df["season_type"] == "REG")
            ]
        
        player_df = player_df[PLAYER_COLS]
        
        defense_df = defense_df.copy()
        defense_df = defense_df[DEFENSE_COLS]
        defense_df = defense_df.rename(
            columns={"opponent_team": "defense_team"}
        )
        
        combined_df = player_df.merge(
            defense_df,
            left_on=[
                "opponent_team",
                "season",
                "week",
                "position",
            ],
            right_on=[
                "defense_team",
                "season",
                "week",
                "position",
            ],
            how="left",
        )
        
        combined_df[self.feature_cols] = (
            combined_df[self.feature_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
        )
        
        combined_df = combined_df.sort_values(
            ["player_id", "season", "week"]
        ).reset_index(drop=True)
        
        features_df = combined_df[self.feature_cols]

        if self.scaler is None:
            self.scaler = StandardScaler()
            features_df = self.scaler.fit_transform(features_df)
        else:
            features_df = self.scaler.transform(features_df)

        combined_df[self.feature_cols] = features_df
        
        for (_, _), player_season_df in combined_df.groupby(
            ["player_id", "season"]
        ):
            player_season_df = player_season_df.sort_values("week")

            features = player_season_df[
                self.feature_cols
            ].to_numpy(dtype=np.float32)

            targets = player_season_df[
                "fantasy_points_ppr"
            ].to_numpy(dtype=np.float32)

            for target_index in range(
                self.sequence_length,
                len(player_season_df),
            ):
                start_index = target_index - self.sequence_length

                sequence = features[start_index:target_index]
                target = targets[target_index]

                self.sequences.append(sequence)
                self.targets.append(target)
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, index: int):
        x = torch.tensor(self.sequences[index], dtype=torch.float32)
        y = torch.tensor(self.targets[index], dtype=torch.float32)
        
        return x, y
    
    