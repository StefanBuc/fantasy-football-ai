import numpy as np
import pandas as pd
from pathlib import Path
import torch
from torch.utils.data import Dataset
from sklearn.preprocessing import StandardScaler

from app.services.defense_features import build_pregame_defense_features

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

DEFENSE_FEATURE_COLS = [
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
    def __init__(
        self,
        player_df: pd.DataFrame,
        defense_df: pd.DataFrame,
        feature_cols: list[str],
        sequence_length: int = 5,
        position: str | None = None,
        seasons: list[int] | None = None,
        scaler: StandardScaler | None = None,
        matchup_scaler: StandardScaler | None = None,
    ):
        self.position = position
        self.feature_cols = list(feature_cols)
        self.matchup_feature_cols = list(DEFENSE_FEATURE_COLS)
        self.sequence_length = sequence_length

        self.scaler = scaler
        self.matchup_scaler = matchup_scaler

        sequences: list[np.ndarray] = []
        matchups: list[np.ndarray] = []
        targets_list: list[float] = []

        player_df = player_df.copy()
        defense_df = defense_df.copy()

        # Filter seasons before merging.
        if seasons is not None:
            player_df = player_df[
                player_df["season"].isin(seasons)
            ].copy()

            defense_df = defense_df[
                defense_df["season"].isin(seasons)
            ].copy()

        # Exclude postseason games.
        player_df = player_df[
            player_df["season_type"] == "REG"
        ].copy()

        # Build a position-specific dataset when requested.
        if position is not None:
            player_df = player_df[
                player_df["position"] == position
            ].copy()

        missing_player_cols = [
            column
            for column in PLAYER_COLS
            if column not in player_df.columns
        ]

        if missing_player_cols:
            raise ValueError(
                f"Missing player columns: {missing_player_cols}"
            )

        missing_defense_cols = [
            column
            for column in DEFENSE_COLS
            if column not in defense_df.columns
        ]

        if missing_defense_cols:
            raise ValueError(
                f"Missing defense columns: {missing_defense_cols}"
            )

        player_df = player_df[PLAYER_COLS].copy()
        defense_df = build_pregame_defense_features(defense_df)

        defense_df = (
            defense_df[DEFENSE_COLS]
            .rename(
                columns={
                    "opponent_team": "defense_team",
                }
            )
            .copy()
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
            validate="many_to_one",
        )

        # Keep the target unscaled.
        combined_df["target_points"] = (
            combined_df["fantasy_points_ppr"].astype(float)
        )

        missing_features = [
            column
            for column in self.feature_cols
            if column not in combined_df.columns
        ]

        if missing_features:
            raise ValueError(
                f"Missing feature columns: {missing_features}"
            )

        # Clean sequence features.
        combined_df[self.feature_cols] = (
            combined_df[self.feature_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(float)
        )

        # Clean upcoming-matchup features independently.
        combined_df[self.matchup_feature_cols] = (
            combined_df[self.matchup_feature_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(float)
        )

        combined_df = combined_df.sort_values(
            [
                "player_id",
                "season",
                "week",
            ]
        ).reset_index(drop=True)

        sequence_features_df = combined_df[
            self.feature_cols
        ].copy()

        matchup_features_df = combined_df[
            self.matchup_feature_cols
        ].copy()

        # Fit sequence scaler only on training data.
        if self.scaler is None:
            self.scaler = StandardScaler()

            scaled_sequence_features = (
                self.scaler.fit_transform(
                    sequence_features_df
                )
            )
        else:
            scaled_sequence_features = (
                self.scaler.transform(
                    sequence_features_df
                )
            )

        # Fit matchup scaler only on training data.
        if self.matchup_scaler is None:
            self.matchup_scaler = StandardScaler()

            scaled_matchup_features = (
                self.matchup_scaler.fit_transform(
                    matchup_features_df
                )
            )
        else:
            scaled_matchup_features = (
                self.matchup_scaler.transform(
                    matchup_features_df
                )
            )

        # Sequence features remain inside combined_df.
        combined_df.loc[
            :,
            self.feature_cols,
        ] = scaled_sequence_features

        # Store matchup features separately so overlapping columns do
        # not overwrite sequence-scaled values.
        scaled_matchup_df = pd.DataFrame(
            scaled_matchup_features,
            columns=self.matchup_feature_cols,
            index=combined_df.index,
        )

        for _, player_season_df in combined_df.groupby(
            [
                "player_id",
                "season",
            ],
            sort=False,
        ):
            player_season_df = player_season_df.sort_values(
                "week"
            )

            player_indices = player_season_df.index

            features = player_season_df[
                self.feature_cols
            ].to_numpy(dtype=np.float32)

            matchup_features = scaled_matchup_df.loc[
                player_indices,
                self.matchup_feature_cols,
            ].to_numpy(dtype=np.float32)

            targets = player_season_df[
                "target_points"
            ].to_numpy(dtype=np.float32)

            for target_index in range(
                self.sequence_length,
                len(player_season_df),
            ):
                start_index = (
                    target_index - self.sequence_length
                )

                # Previous five games.
                sequences.append(
                    features[start_index:target_index]
                )

                # Opponent defensive profile for the target game.
                matchups.append(
                    matchup_features[target_index]
                )

                # Actual fantasy points in the target game.
                targets_list.append(
                    targets[target_index]
                )

        if not sequences:
            raise ValueError(
                "No sequences were created. Check the seasons, "
                "position, filters, and sequence length."
            )

        self.sequences = torch.tensor(
            np.asarray(sequences),
            dtype=torch.float32,
        )

        self.matchups = torch.tensor(
            np.asarray(matchups),
            dtype=torch.float32,
        )

        self.targets = torch.tensor(
            np.asarray(targets_list),
            dtype=torch.float32,
        )

        if not (
            len(self.sequences)
            == len(self.matchups)
            == len(self.targets)
        ):
            raise RuntimeError(
                "Sequence, matchup, and target counts do not match."
            )

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(
        self,
        index: int,
    ) -> tuple[
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
    ]:
        return (
            self.sequences[index],
            self.matchups[index],
            self.targets[index],
        )
