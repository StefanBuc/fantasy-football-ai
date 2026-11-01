from typing import cast
from uuid import uuid4
from app.services.result_cache import ResultCache
from app.services.performance import timed_stage

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
    def __init__(self, season: int):
        self.season = season
        self.generation = uuid4().hex

        self.data = NFLData(
            [
                season - 1,
                season,
            ]
        )

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

        # Models are created only when their position
        # is requested, then reused.
        self.position_services: dict[
            str,
            PyTorchProjectionService | SpecialTeamsProjectionService,
        ] = {}
        self.special_teams_data = None
        self.weekly_cache = ResultCache[ProjectionSlateResult](name="weekly")

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
                        load_special_teams_weekly(
                            [self.season - 1, self.season]
                        )
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
