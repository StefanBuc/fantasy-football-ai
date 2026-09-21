from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

from app.integrations.espn_player_matching import (
    ESPNPlayerMatch,
    match_espn_player,
)
from app.services.projection_types import (
    PlayerProjectionRequest,
    ProjectionSlateResult,
)

if TYPE_CHECKING:
    from app.services.weekly_projection_service import (
        WeeklyProjectionService,
    )


RosterProjectionStatus = Literal[
    "projected",
    "skipped",
]


@dataclass(frozen=True)
class ESPNRosterProjection:
    espn_id: int
    player_id: str | None
    player_name: str
    position: str
    lineup_slot: str
    team: str | None
    opponent_team: str | None
    predicted_points: float | None
    status: RosterProjectionStatus
    reason: str | None = None


@dataclass(frozen=True)
class ESPNRosterPlayer:
    espn_id: int
    player_name: str
    position: str
    lineup_slot: str


def build_espn_projection_request(
    player_match: ESPNPlayerMatch,
    roster_df: pd.DataFrame,
    opponents: dict[str, str],
    season: int,
    week: int,
) -> tuple[PlayerProjectionRequest | None, str | None]:
    if (
        player_match.status != "matched"
        or player_match.player_id is None
    ):
        return (
            None,
            player_match.reason
            or "ESPN player was not matched to an NFL player.",
        )

    required_columns = {
        "player_id",
        "player_name",
        "position",
        "team",
    }

    missing_columns = (
        required_columns - set(roster_df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"NFL roster is missing columns: "
            f"{sorted(missing_columns)}"
        )

    player_rows = roster_df[
        roster_df["player_id"].astype(str)
        == player_match.player_id
    ]

    if player_rows.empty:
        return (
            None,
            "Player is not on the active NFL roster "
            f"for {season} week {week}.",
        )

    if len(player_rows) != 1:
        raise ValueError(
            f"Player {player_match.player_id} appears "
            "more than once in the NFL weekly roster."
        )

    player = next(
        player_rows.itertuples(index=False)
    )

    team = str(player.team).upper()
    opponent = opponents.get(team)

    if opponent is None:
        return (
            None,
            f"{team} does not play during week {week}.",
        )

    request = PlayerProjectionRequest(
        player_id=player_match.player_id,
        player_name=player_match.espn_name,
        team=team,
        season=season,
        upcoming_week=week,
        opponent_team=opponent,
    )

    return request, None


def build_espn_request_batches(
    player_matches: list[ESPNPlayerMatch],
    roster_df: pd.DataFrame,
    opponents: dict[str, str],
    season: int,
    week: int,
) -> tuple[
    dict[str, list[PlayerProjectionRequest]],
    dict[int, str],
]:
    requests_by_position: dict[
        str,
        list[PlayerProjectionRequest],
    ] = {
        "QB": [],
        "RB": [],
        "WR": [],
        "TE": [],
    }

    skipped: dict[int, str] = {}

    for player_match in player_matches:
        position = player_match.position.upper()

        if position not in requests_by_position:
            skipped[player_match.espn_id] = (
                f"Unsupported position: {position}"
            )
            continue

        request, reason = build_espn_projection_request(
            player_match=player_match,
            roster_df=roster_df,
            opponents=opponents,
            season=season,
            week=week,
        )

        if request is None:
            skipped[player_match.espn_id] = (
                reason or "Projection request could not be built."
            )
            continue

        requests_by_position[position].append(
            request
        )

    return requests_by_position, skipped


def project_espn_request_batches(
    weekly_service: "WeeklyProjectionService",
    requests_by_position: dict[
        str,
        list[PlayerProjectionRequest],
    ],
) -> dict[str, ProjectionSlateResult]:
    results: dict[str, ProjectionSlateResult] = {}

    for position, requests in (
        requests_by_position.items()
    ):
        if not requests:
            continue

        results[position] = (
            weekly_service.project_requests(
                position=position,
                requests=requests,
            )
        )

    return results


def project_espn_roster(
    weekly_service: "WeeklyProjectionService",
    roster_players: list[ESPNRosterPlayer],
    id_map: pd.DataFrame,
    roster_df: pd.DataFrame,
    opponents: dict[str, str],
    season: int,
    week: int,
) -> list[ESPNRosterProjection]:
    player_matches = [
        match_espn_player(
            id_map=id_map,
            espn_id=player.espn_id,
            espn_name=player.player_name,
            position=player.position,
        )
        for player in roster_players
    ]

    requests_by_position, request_skips = (
        build_espn_request_batches(
            player_matches=player_matches,
            roster_df=roster_df,
            opponents=opponents,
            season=season,
            week=week,
        )
    )

    batch_results = project_espn_request_batches(
        weekly_service=weekly_service,
        requests_by_position=requests_by_position,
    )

    requests_by_player_id = {
        request.player_id: request
        for requests in requests_by_position.values()
        for request in requests
    }

    predictions_by_player_id = {
        projection.request.player_id: projection.predicted_points
        for result in batch_results.values()
        for projection in result.projections
    }

    model_skips_by_player_id = {
        skipped.request.player_id: skipped.reason
        for result in batch_results.values()
        for skipped in result.skipped
    }

    projections = []

    for roster_player, player_match in zip(
        roster_players,
        player_matches,
    ):
        player_id = player_match.player_id
        request = (
            requests_by_player_id.get(player_id)
            if player_id is not None
            else None
        )

        predicted_points = (
            predictions_by_player_id.get(player_id)
            if player_id is not None
            else None
        )

        reason = player_match.reason

        if reason is None:
            reason = request_skips.get(
                roster_player.espn_id
            )

        if reason is None and player_id is not None:
            reason = model_skips_by_player_id.get(
                player_id
            )

        if predicted_points is None and reason is None:
            reason = "No projection result was produced."

        projections.append(
            ESPNRosterProjection(
                espn_id=roster_player.espn_id,
                player_id=player_id,
                player_name=roster_player.player_name,
                position=roster_player.position,
                lineup_slot=roster_player.lineup_slot,
                team=(
                    request.team
                    if request is not None
                    else None
                ),
                opponent_team=(
                    request.opponent_team
                    if request is not None
                    else None
                ),
                predicted_points=predicted_points,
                status=(
                    "projected"
                    if predicted_points is not None
                    else "skipped"
                ),
                reason=reason,
            )
        )

    return projections
