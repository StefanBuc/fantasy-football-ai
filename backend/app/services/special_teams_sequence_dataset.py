import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset


def game_is_before(
    frame: pd.DataFrame,
    season: int,
    week: int,
) -> pd.Series:
    return (frame["season"] < season) | (
        (frame["season"] == season)
        & (frame["week"] < week)
    )


def build_special_teams_matchup(
    weekly_df: pd.DataFrame,
    opponent_team: str,
    season: int,
    week: int,
    matchup_sources: dict[str, str],
    window: int = 5,
) -> dict[str, float]:
    opponent_history = weekly_df[
        (weekly_df["opponent_team"] == opponent_team)
        & game_is_before(weekly_df, season, week)
    ].copy()

    opponent_history = (
        opponent_history.sort_values(["season", "week"])
        .tail(window)
    )

    return {
        output_column: (
            float(opponent_history[source_column].mean())
            if not opponent_history.empty
            else 0.0
        )
        for output_column, source_column in matchup_sources.items()
    }


class SpecialTeamsSequenceDataset(Dataset):
    def __init__(
        self,
        weekly_df: pd.DataFrame,
        feature_cols: list[str],
        matchup_sources: dict[str, str],
        sequence_length: int = 5,
        seasons: list[int] | None = None,
        target_seasons: list[int] | None = None,
        scaler: StandardScaler | None = None,
        matchup_scaler: StandardScaler | None = None,
    ):
        self.feature_cols = list(feature_cols)
        self.matchup_sources = dict(matchup_sources)
        self.matchup_feature_cols = list(matchup_sources)
        self.sequence_length = sequence_length
        self.scaler = scaler
        self.matchup_scaler = matchup_scaler

        source = weekly_df.copy()
        if seasons is not None:
            source = source[source["season"].isin(seasons)].copy()

        required = {
            "entity_id",
            "entity_name",
            "team",
            "opponent_team",
            "season",
            "week",
            "fantasy_points",
            *self.feature_cols,
            *self.matchup_sources.values(),
        }
        missing = required - set(source.columns)
        if missing:
            raise ValueError(
                f"Special-teams data is missing columns: {sorted(missing)}"
            )

        target_season_set = (
            set(target_seasons)
            if target_seasons is not None
            else None
        )

        source[self.feature_cols] = (
            source[self.feature_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(float)
        )
        source = source.sort_values(
            ["entity_id", "season", "week"]
        ).reset_index(drop=True)

        raw_sequences: list[np.ndarray] = []
        raw_matchups: list[list[float]] = []
        targets: list[float] = []
        metadata: list[dict[str, object]] = []

        for _, history in source.groupby("entity_id", sort=False):
            history = history.sort_values(["season", "week"])

            for target_index in range(sequence_length, len(history)):
                target = history.iloc[target_index]
                target_season = int(target["season"])

                if (
                    target_season_set is not None
                    and target_season not in target_season_set
                ):
                    continue

                start = target_index - sequence_length
                raw_sequences.append(
                    history.iloc[start:target_index][self.feature_cols]
                    .to_numpy(dtype=np.float32)
                )

                matchup = build_special_teams_matchup(
                    weekly_df=source,
                    opponent_team=str(target["opponent_team"]),
                    season=target_season,
                    week=int(target["week"]),
                    matchup_sources=self.matchup_sources,
                )
                raw_matchups.append(
                    [matchup[column] for column in self.matchup_feature_cols]
                )
                targets.append(float(target["fantasy_points"]))
                metadata.append(
                    {
                        "entity_id": str(target["entity_id"]),
                        "entity_name": str(target["entity_name"]),
                        "season": target_season,
                        "week": int(target["week"]),
                        "opponent_team": str(target["opponent_team"]),
                    }
                )

        if not raw_sequences:
            raise ValueError(
                "No special-teams sequences were created. Check the "
                "seasons and sequence length."
            )

        sequence_array = np.asarray(raw_sequences, dtype=np.float32)
        matchup_array = np.asarray(raw_matchups, dtype=np.float32)
        sample_count, history_length, feature_count = sequence_array.shape

        if self.scaler is None:
            self.scaler = StandardScaler()
            scaled_sequences = self.scaler.fit_transform(
                sequence_array.reshape(-1, feature_count)
            )
        else:
            scaled_sequences = self.scaler.transform(
                sequence_array.reshape(-1, feature_count)
            )

        if self.matchup_scaler is None:
            self.matchup_scaler = StandardScaler()
            scaled_matchups = self.matchup_scaler.fit_transform(
                matchup_array
            )
        else:
            scaled_matchups = self.matchup_scaler.transform(
                matchup_array
            )

        self.sequences = torch.tensor(
            scaled_sequences.reshape(
                sample_count,
                history_length,
                feature_count,
            ),
            dtype=torch.float32,
        )
        self.matchups = torch.tensor(
            scaled_matchups,
            dtype=torch.float32,
        )
        self.targets = torch.tensor(targets, dtype=torch.float32)
        self.sample_metadata = metadata

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(
        self,
        index: int,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return (
            self.sequences[index],
            self.matchups[index],
            self.targets[index],
        )
