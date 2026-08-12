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

def merge_player_defense_features(
    player_df: pd.DataFrame,
    defense_df: pd.DataFrame,
) -> pd.DataFrame:
    player_features = player_df[PLAYER_COLS].copy()

    defense_features = build_pregame_defense_features(
        defense_df
    )

    defense_features = (
        defense_features[DEFENSE_COLS]
        .rename(
            columns={
                "opponent_team": "defense_team",
            }
        )
        .copy()
    )

    return player_features.merge(
        defense_features,
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
    
def build_player_history(
    player_df: pd.DataFrame,
    defense_df: pd.DataFrame,
    player_id: str,
    season: int,
    upcoming_week: int,
    position: str,
    feature_cols: list[str],
    sequence_length: int,
) -> list[dict[str, float]]:
    game_is_before_prediction = (
        (player_df["season"] < season)
        | (
            (player_df["season"] == season)
            & (player_df["week"] < upcoming_week)
        )
    )

    previous_games = player_df[
        (player_df["player_id"] == player_id)
        & (player_df["season_type"] == "REG")
        & (player_df["position"] == position)
        & game_is_before_prediction
    ].copy()

    combined_df = merge_player_defense_features(
        previous_games,
        defense_df,
    )

    combined_df = (
        combined_df
        .sort_values(["season", "week"])
        .tail(sequence_length)
        .copy()
    )

    if len(combined_df) != sequence_length:
        raise ValueError(
            f"Player {player_id} has only {len(combined_df)} "
            f"games before week {upcoming_week}; "
            f"{sequence_length} are required."
        )

    missing_features = [
        column
        for column in feature_cols
        if column not in combined_df.columns
    ]

    if missing_features:
        raise ValueError(
            f"Missing history features: {missing_features}"
        )

    combined_df[feature_cols] = (
        combined_df[feature_cols]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .astype(float)
    )
    
    feature_values = combined_df[feature_cols].to_numpy(dtype=np.float32)

    return [
        {
            column: float(value)
            for column, value in zip(feature_cols, row)
        }
        for row in feature_values
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
        target_seasons: list[int] | None = None,
        scaler: StandardScaler | None = None,
        matchup_scaler: StandardScaler | None = None,
    ):
        self.position = position
        self.feature_cols = list(feature_cols)
        self.matchup_feature_cols = list(DEFENSE_FEATURE_COLS)
        self.sequence_length = sequence_length

        self.scaler = scaler
        self.matchup_scaler = matchup_scaler
        self.target_seasons = (set(target_seasons) if target_seasons is not None else None)

        sequences: list[np.ndarray] = []
        matchups: list[np.ndarray] = []
        targets_list: list[float] = []
        sample_metadata = []

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

        combined_df = merge_player_defense_features(
            player_df=player_df,
            defense_df=defense_df,
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
                    sequence_features_df.to_numpy()
                )
            )
        else:
            scaled_sequence_features = (
                self.scaler.transform(
                    sequence_features_df.to_numpy()
                )
            )

        # Fit matchup scaler only on training data.
        if self.matchup_scaler is None:
            self.matchup_scaler = StandardScaler()

            scaled_matchup_features = (
                self.matchup_scaler.fit_transform(
                    matchup_features_df.to_numpy()
                )
            )
        else:
            scaled_matchup_features = (
                self.matchup_scaler.transform(
                    matchup_features_df.to_numpy()
                )
            )

        # Store sequence features separately so overlapping columns do
        # not overwrite matchup-scaled values.
        scaled_sequence_df = pd.DataFrame(
            scaled_sequence_features,
            columns=self.feature_cols,
            index=combined_df.index,
        )

        # Store matchup features separately so overlapping columns do
        # not overwrite sequence-scaled values.
        scaled_matchup_df = pd.DataFrame(
            scaled_matchup_features,
            columns=self.matchup_feature_cols,
            index=combined_df.index,
        )

        for _, player_history_df in combined_df.groupby(
            "player_id",
            sort=False,
        ):
            player_history_df = player_history_df.sort_values(
                ["season", "week"]
            )

            player_indices = player_history_df.index

            features = scaled_sequence_df.loc[
                player_indices,
                self.feature_cols,
            ].to_numpy(dtype=np.float32)

            matchup_features = scaled_matchup_df.loc[
                player_indices,
                self.matchup_feature_cols,
            ].to_numpy(dtype=np.float32)

            targets = player_history_df[
                "target_points"
            ].to_numpy(dtype=np.float32)

            for target_index in range(
                self.sequence_length,
                len(player_history_df),
            ):
                target_row = player_history_df.iloc[target_index]
                target_season = int(target_row["season"])
                
                if (self.target_seasons is not None
                    and target_season not in self.target_seasons
                ):
                    continue

                sample_metadata.append({
                    "player_id": target_row["player_id"],
                    "player_name": target_row["player_name"],
                    "season": int(target_row["season"]),
                    "week": int(target_row["week"]),
                    "opponent_team": target_row["opponent_team"],
                })
                
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
        self.sample_metadata = sample_metadata

        if not (
            len(self.sequences)
            == len(self.matchups)
            == len(self.targets)
            == len(self.sample_metadata)
        ):
            raise RuntimeError(
                "Sequence, matchup, target and metadata counts do not match."
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
