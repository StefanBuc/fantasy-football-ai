from bisect import bisect_left

import numpy as np

from app.services.projection_types import PlayerProjectionRequest
from app.services.pytorch_projection_model import (
    load_selected_projection_checkpoint,
    predict_batch_from_raw_features,
)
from app.services.special_teams_sequence_dataset import (
    build_special_teams_matchup,
)


class SpecialTeamsProjectionService:
    def __init__(self, position: str, weekly_df, device=None):
        normalized_position = position.upper()
        if normalized_position not in {"K", "DST"}:
            raise ValueError(f"Unsupported position: {position}")

        (
            self.model,
            self.sequence_scaler,
            self.matchup_scaler,
            self.checkpoint,
            self.device,
        ) = load_selected_projection_checkpoint(
            position=normalized_position,
            device=device,
        )

        self.position = normalized_position
        self.weekly_df = weekly_df.copy()
        self.feature_cols = list(self.checkpoint["feature_cols"])
        self.matchup_sources = dict(self.checkpoint["matchup_sources"])
        self.matchup_cache: dict[
            tuple[str, int, int], dict[str, float]
        ] = {}
        self.history_by_entity: dict[
            str,
            tuple[
                list[tuple[int, int]],
                list[dict[str, float]],
            ],
        ] = {}

        cleaned = self.weekly_df.copy()
        cleaned[self.feature_cols] = (
            cleaned[self.feature_cols]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(float)
        )

        for entity_id, history in cleaned.groupby(
            "entity_id",
            sort=False,
        ):
            history = history.sort_values(["season", "week"])
            game_keys = [
                (int(season), int(week))
                for season, week in zip(
                    history["season"],
                    history["week"],
                )
            ]
            feature_values = history[self.feature_cols].to_numpy(
                dtype=np.float32
            )
            records = [
                {
                    column: float(value)
                    for column, value in zip(self.feature_cols, row)
                }
                for row in feature_values
            ]
            self.history_by_entity[str(entity_id)] = (
                game_keys,
                records,
            )

        if self.position == "K":
            team_history = (
                cleaned.groupby(
                    ["team", "season", "week"],
                    as_index=False,
                ).agg(
                    {
                        column: "sum"
                        for column in self.feature_cols
                        if column != "week"
                    }
                )
            )

            for team, history in team_history.groupby(
                "team",
                sort=False,
            ):
                history = history.sort_values(["season", "week"])
                game_keys = [
                    (int(season), int(week))
                    for season, week in zip(
                        history["season"],
                        history["week"],
                    )
                ]
                feature_values = history[
                    self.feature_cols
                ].to_numpy(dtype=np.float32)
                records = [
                    {
                        column: float(value)
                        for column, value in zip(
                            self.feature_cols,
                            row,
                        )
                    }
                    for row in feature_values
                ]
                self.history_by_entity[f"TEAM:{team}"] = (
                    game_keys,
                    records,
                )

    def history_games_available(
        self,
        request: PlayerProjectionRequest,
    ) -> int:
        stored = self.history_by_entity.get(request.player_id)
        if stored is None:
            return 0

        game_keys, _ = stored
        return bisect_left(
            game_keys,
            (request.season, request.upcoming_week),
        )

    def _get_history(
        self,
        request: PlayerProjectionRequest,
    ) -> list[dict[str, float]]:
        stored = self.history_by_entity.get(request.player_id)
        if stored is None:
            return []

        game_keys, records = stored
        end = bisect_left(
            game_keys,
            (request.season, request.upcoming_week),
        )
        start = max(
            0,
            end - int(self.checkpoint["sequence_length"]),
        )
        return records[start:end]

    def _get_matchup(
        self,
        request: PlayerProjectionRequest,
    ) -> dict[str, float]:
        key = (
            request.opponent_team,
            request.season,
            request.upcoming_week,
        )
        if key not in self.matchup_cache:
            self.matchup_cache[key] = build_special_teams_matchup(
                weekly_df=self.weekly_df,
                opponent_team=request.opponent_team,
                season=request.season,
                week=request.upcoming_week,
                matchup_sources=self.matchup_sources,
            )
        return self.matchup_cache[key]

    def predict_many(
        self,
        requests: list[PlayerProjectionRequest],
    ) -> list[float]:
        return predict_batch_from_raw_features(
            model=self.model,
            sequence_scaler=self.sequence_scaler,
            matchup_scaler=self.matchup_scaler,
            checkpoint=self.checkpoint,
            device=self.device,
            histories=[self._get_history(request) for request in requests],
            matchups=[self._get_matchup(request) for request in requests],
        )
