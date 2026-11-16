from typing import cast
from uuid import uuid4
from hashlib import sha256
from app.services.data_snapshot import (
    source_fingerprint, model_fingerprint, encode_frames, decode_frames, FrameSnapshot,
)
from app.services.snapshot_nfl_data import SnapshotNFLData
from app.services.disk_cache import disk_cache
from app.services.result_cache import ResultCache
from app.services.performance import logger, timed_stage

from app.services.pytorch_inference import (
    PyTorchProjectionService,
)
from app.services.NFL_data import NFLData
from app.services.projection_slate import (
    build_projection_requests,
    project_position_slate,
)
from app.services.projection_types import (
    PlayerProjectionRequest,
    ProjectionSlateResult,
)
from app.services.special_teams_data import (
    load_special_teams_weekly,
)
from app.services.special_teams_inference import (
    SpecialTeamsProjectionService,
)

SUPPORTED_POSITIONS = {
    "QB",
    "RB",
    "WR",
    "TE",
    "K",
    "DST",
}

'''
    A service for projecting player performance for a specific week and position.
'''


class WeeklyProjectionService:
    def __init__(self, season: int, refresh: bool = False):
        self.season = season
        self._data_generation = uuid4().hex
        self._snapshot_key = (season, source_fingerprint())

        self.data = NFLData(
            [
                season - 1,
                season,
            ]
        )

        restored = False if refresh else self._restore_snapshot()
        if not restored:
            self._load_data(season)
            self._save_snapshot()
        self.generation = sha256(
            f"{self._data_generation}:{model_fingerprint()}".encode()
        ).hexdigest()

        # Models stay lazy; cached projections need no checkpoint loading.
        self.position_services: dict[
            str, PyTorchProjectionService | SpecialTeamsProjectionService,
        ] = {}
        self.special_teams_data = None
        self.weekly_cache = ResultCache[ProjectionSlateResult](
            name="weekly", persistent_key=self.generation,
        )

    def _load_data(self, season: int) -> None:
        for stage, loader in (
            ("nfl_data", self.data.load_data),
            ("schedule", self.data.load_schedule),
            ("rosters", self.data.load_weekly_rosters),
            ("depth_charts", self.data.load_depth_charts),
        ):
            with timed_stage(stage, season=season):
                loader()

        with timed_stage("player_features", season=season):
            self.player_df = self.data.get_player_stats()
        with timed_stage("defense_features", season=season):
            self.defense_df = self.data.get_defense_stats()

    _SNAPSHOT_FIELDS = ("weekly", "snap_counts", "ids", "schedule",
                        "weekly_rosters", "depth_charts")

    def __getattr__(self, name):
        table = {"player_df": "player_features", "defense_df": "defense_features"}.get(name)
        snapshot = self.__dict__.get("_snapshot")
        if table is not None and snapshot is not None:
            frame = snapshot[table]
            setattr(self, name, frame)
            return frame
        raise AttributeError(name)

    def _restore_snapshot(self) -> bool:
        payload = disk_cache.get("nfl_data", self._snapshot_key)
        if payload is None:
            return False
        try:
            with timed_stage("restore_nfl_snapshot", season=self.season):
                snapshot = FrameSnapshot(payload)
                required = {*self._SNAPSHOT_FIELDS, "player_features", "defense_features"}
                if not required.issubset(snapshot.names):
                    raise ValueError("Incomplete NFL snapshot")
                self._data_generation = snapshot.metadata["generation"]
                self._snapshot = snapshot
                self.data = SnapshotNFLData([self.season - 1, self.season], snapshot, self._SNAPSHOT_FIELDS)
            return True
        except Exception as error:
            logger.warning("Invalid NFL snapshot; reloading data: %s", error)
            return False

    def _save_snapshot(self) -> None:
        try:
            frames = {name: getattr(self.data, name) for name in self._SNAPSHOT_FIELDS}
            frames.update(player_features=self.player_df, defense_features=self.defense_df)
            disk_cache.put("nfl_data", self._snapshot_key,
                           encode_frames(frames, {"generation": self._data_generation}),
                           ttl_seconds=6 * 3600, max_entries=4)
        except Exception as error:
            logger.warning("Cannot persist NFL snapshot; using memory: %s", error)

    def _load_special_teams_data(self):
        key = (self.season, self._data_generation)
        payload = disk_cache.get("special_teams", key)
        if payload is not None:
            try:
                frames, _ = decode_frames(payload)
                if {"K", "DST"}.issubset(frames):
                    return frames
            except Exception as error:
                logger.warning("Invalid special-teams snapshot; rebuilding: %s", error)
        frames = load_special_teams_weekly([self.season - 1, self.season])
        try:
            disk_cache.put("special_teams", key, encode_frames(frames, {}),
                           ttl_seconds=6 * 3600, max_entries=4)
        except Exception as error:
            logger.warning("Cannot persist special-teams snapshot: %s", error)
        return frames

    def _get_position_service(
        self,
        position: str,
    ) -> PyTorchProjectionService | SpecialTeamsProjectionService:
        normalized_position = position.upper()

        if (
            normalized_position
            not in SUPPORTED_POSITIONS
        ):
            raise ValueError(
                f"Unsupported position: {position}"
            )

        if (
            normalized_position
            not in self.position_services
        ):
            if normalized_position in {"K", "DST"}:
                if self.special_teams_data is None:
                    self.special_teams_data = (
                        self._load_special_teams_data()
                    )

                self.position_services[normalized_position] = (
                    SpecialTeamsProjectionService(
                        position=normalized_position,
                        weekly_df=self.special_teams_data[
                            normalized_position
                        ],
                    )
                )
            else:
                self.position_services[normalized_position] = (
                    PyTorchProjectionService(
                        position=normalized_position,
                        player_df=self.player_df,
                        defense_df=self.defense_df,
                    )
                )

        return self.position_services[
            normalized_position
        ]

    def project_requests(
        self,
        position: str,
        requests: list[PlayerProjectionRequest],
    ) -> ProjectionSlateResult:
        normalized_position = position.upper()

        with timed_stage("position_service", season=self.season,
                         position=normalized_position):
            service = self._get_position_service(normalized_position)

        with timed_stage("projection_batch", season=self.season,
                         position=normalized_position, players=len(requests)):
            return project_position_slate(
                service=cast(PyTorchProjectionService, service),
                requests=requests,
            )

    def project_week(
        self,
        week: int,
        position: str,
    ) -> ProjectionSlateResult:
        if week < 1 or week > 18:
            raise ValueError(
                "Week must be between 1 and 18."
            )

        normalized_position = position.upper()

        return self.weekly_cache.get_or_create(
            (self.season, week, normalized_position),
            lambda: self._project_week_uncached(week, normalized_position),
        )

    def _project_week_uncached(
        self,
        week: int,
        normalized_position: str,
    ) -> ProjectionSlateResult:
        roster_df = self.data.get_week_roster(
            season=self.season,
            week=week,
        )

        opponents = self.data.get_week_opponents(
            season=self.season,
            week=week,
        )

        depth_chart_df = (
            self.data.get_week_depth_chart(
                season=self.season,
                week=week,
            )
        )

        with timed_stage("projection_requests", season=self.season,
                         week=week, position=normalized_position):
            requests = build_projection_requests(
                roster_df=roster_df,
                opponents=opponents,
                position=normalized_position,
                depth_chart_df=depth_chart_df,
            )

        return self.project_requests(
            position=normalized_position,
            requests=requests,
        )
