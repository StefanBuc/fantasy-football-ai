from app.services.pytorch_inference import (
    PyTorchProjectionService,
)
from app.services.NFL_data import NFLData
from app.services.projection_slate import (
    build_projection_requests,
    project_position_slate,
)
from app.services.projection_types import (
    ProjectionSlateResult,
)

SUPPORTED_POSITIONS = {
    "QB",
    "RB",
    "WR",
    "TE",
}

'''
    A service for projecting player performance for a specific week and position.
'''


class WeeklyProjectionService:
    def __init__(self, season: int):
        self.season = season

        self.data = NFLData(
            [
                season - 1,
                season,
            ]
        )

        self.data.load_data()
        self.data.load_schedule()
        self.data.load_weekly_rosters()
        self.data.load_depth_charts()

        self.player_df = (
            self.data.get_player_stats()
        )

        self.defense_df = (
            self.data.get_defense_stats()
        )

        # Models are created only when their position
        # is requested, then reused.
        self.position_services: dict[
            str,
            PyTorchProjectionService,
        ] = {}

    def _get_position_service(
        self,
        position: str,
    ) -> PyTorchProjectionService:
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
            self.position_services[
                normalized_position
            ] = PyTorchProjectionService(
                position=normalized_position,
                player_df=self.player_df,
                defense_df=self.defense_df,
            )

        return self.position_services[
            normalized_position
        ]

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

        service = self._get_position_service(
            normalized_position
        )

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

        requests = build_projection_requests(
            roster_df=roster_df,
            opponents=opponents,
            position=normalized_position,
            depth_chart_df=depth_chart_df,
        )

        return project_position_slate(
            service=service,
            requests=requests,
        )