import pandas as pd

from typing import TYPE_CHECKING

from app.services.projection_types import (
    PlayerProjection,
    PlayerProjectionRequest,
    ProjectionSlateResult,
    SkippedPlayerProjection,
)

if TYPE_CHECKING:
    from app.services.pytorch_inference import (
        PyTorchProjectionService,
    )
    
ACTIVE_DEPTH_LIMITS = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 2,
}

def build_projection_requests(
    roster_df: pd.DataFrame,
    opponents: dict[str, str],
    position: str,
    depth_chart_df: pd.DataFrame | None = None,
) -> list[PlayerProjectionRequest]:
    normalized_position = position.upper()

    if normalized_position not in {
        "QB",
        "RB",
        "WR",
        "TE",
    }:
        raise ValueError(
            f"Unsupported position: {position}"
        )

    required_columns = {
        "player_id",
        "player_name",
        "position",
        "team",
        "season",
        "week",
    }

    missing_columns = (
        required_columns
        - set(roster_df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"Roster is missing columns: "
            f"{sorted(missing_columns)}"
        )

    position_roster = roster_df[
        roster_df["position"]
        == normalized_position
    ]
    
    position_roster = position_roster.copy()

    if depth_chart_df is not None:
        required_depth_columns = {
            "player_id",
            "team",
            "position",
            "depth_position",
            "depth_team",
        }

        missing_depth_columns = (
            required_depth_columns
            - set(depth_chart_df.columns)
        )

        if missing_depth_columns:
            raise ValueError(
                f"Depth chart is missing columns: "
                f"{sorted(missing_depth_columns)}"
            )

        position_depth_chart = depth_chart_df[
            depth_chart_df["position"]
            == normalized_position
        ][
            [
                "player_id",
                "team",
                "position",
                "depth_position",
                "depth_team",
            ]
        ].copy()

        position_roster = position_roster.merge(
            position_depth_chart,
            on=["player_id", "team", "position"],
            how="inner",
            validate="one_to_one",
        )

        position_roster["active_depth_rank"] = (
            position_roster
            .groupby(
                ["team", "depth_position"]
            )["depth_team"]
            .rank(
                method="dense",
                ascending=True,
            )
        )

        depth_limit = ACTIVE_DEPTH_LIMITS[
            normalized_position
        ]

        position_roster = position_roster[
            position_roster["active_depth_rank"]
            <= depth_limit
        ].copy()

    requests = []

    for player in position_roster.itertuples(
        index=False
    ):
        team = str(player.team).upper()
        opponent = opponents.get(team)

        # A team absent from the schedule is on bye.
        if opponent is None:
            continue

        season_value = str(player.season).strip()
        week_value = str(player.week).strip()
        
        depth_position=(
            str(player.depth_position)
            if hasattr(player, "depth_position")
            else None
        )
        depth_team=(
            int(float(str(player.depth_team)))
            if hasattr(player, "depth_team")
            else None
        )
        active_depth_rank=(
            int(float(str(player.active_depth_rank)))
            if hasattr(player, "active_depth_rank")
            else None
        )
        
        requests.append(
            PlayerProjectionRequest(
                player_id=str(player.player_id),
                player_name=str(player.player_name),
                team=team,
                season=int(season_value),
                upcoming_week=int(week_value),
                opponent_team=opponent,
                depth_position=depth_position,
                depth_team=depth_team, 
                active_depth_rank=active_depth_rank,
            )
        )

    return requests

def project_position_slate(
    service: "PyTorchProjectionService",
    requests: list[PlayerProjectionRequest],
) -> ProjectionSlateResult:
    eligible_requests = []
    skipped = []

    required_games = int(
        service.checkpoint["sequence_length"]
    )

    for request in requests:
        available_games = (
            service.history_games_available(
                request
            )
        )

        if available_games < required_games:
            skipped.append(
                SkippedPlayerProjection(
                    request=request,
                    available_games=available_games,
                    required_games=required_games,
                    reason=(
                        f"Requires {required_games} "
                        f"previous games; found "
                        f"{available_games}."
                    ),
                )
            )
            continue

        eligible_requests.append(request)

    predictions = service.predict_many(
        eligible_requests
    )

    projections = [
        PlayerProjection(
            request=request,
            position=service.position,
            predicted_points=prediction,
        )
        for request, prediction in zip(
            eligible_requests,
            predictions,
        )
    ]

    projections.sort(
        key=lambda result: result.predicted_points,
        reverse=True,
    )

    return ProjectionSlateResult(
        projections=projections,
        skipped=skipped,
    )