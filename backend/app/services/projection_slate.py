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

def build_projection_requests(
    roster_df: pd.DataFrame,
    opponents: dict[str, str],
    position: str,
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

        requests.append(
            PlayerProjectionRequest(
                player_id=str(player.player_id),
                player_name=str(player.player_name),
                team=team,
                season=int(season_value),
                upcoming_week=int(week_value),
                opponent_team=opponent,
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