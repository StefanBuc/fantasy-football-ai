from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

import pandas as pd

from app.integrations.espn_player_matching import (
    ESPNPlayerMatch,
    match_espn_player,
)
from app.services.projection_types import (
    PlayerProjectionRequest,
    ProjectionMethod,
    ProjectionSlateResult,
)
from app.services.projection_slate import (
    build_projection_requests,
)
from app.config.model_config import (
    TEAMMATE_INJURY_FEATURE_COLS,
)
from app.services.teammate_injury_features import (
    build_live_team_injury_context,
    empty_injury_context,
    is_unavailable_injury_status,
)

if TYPE_CHECKING:
    from app.services.weekly_projection_service import (
        WeeklyProjectionService,
    )


RosterProjectionStatus = Literal[
    "projected",
    "skipped",
]

SUPPORTED_POSITIONS = {
    "QB",
    "RB",
    "WR",
    "TE",
    "K",
    "DST",
}

NFL_TEAM_CODES = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}


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
    projection_method: ProjectionMethod | None = None
    history_games: int | None = None
    injury_context_used: bool = False
    unavailable_teammates: int = 0
    is_on_bye: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class ESPNRosterPlayer:
    espn_id: int
    player_name: str
    position: str
    lineup_slot: str
    team: str | None = None
    injury_status: str | None = None
    espn_projected_points: float | None = None


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

    if (
        player_match.position == "DST"
        or player_match.player_id.startswith("TEAM:")
    ):
        team = player_match.player_id.replace(
            "TEAM:", "", 1
        ).upper()
        opponent = opponents.get(team)

        if opponent is None:
            return None, f"{team} does not play during week {week}."

        return (
            PlayerProjectionRequest(
                player_id=(
                    player_match.player_id
                    if player_match.player_id.startswith("TEAM:")
                    else team
                ),
                player_name=player_match.espn_name,
                team=team,
                season=season,
                upcoming_week=week,
                opponent_team=opponent,
            ),
            None,
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
        "K": [],
        "DST": [],
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
    depth_chart_df: pd.DataFrame | None = None,
    use_espn_qb_starter_signal: bool = False,
) -> list[ESPNRosterProjection]:
    player_matches = []

    for player in roster_players:
        model_position = (
            "DST"
            if player.position == "D/ST"
            else player.position
        )

        if model_position == "DST":
            player_matches.append(
                ESPNPlayerMatch(
                    espn_id=player.espn_id,
                    espn_name=player.player_name,
                    position="DST",
                    player_id=player.team,
                    status=(
                        "matched"
                        if player.team is not None
                        else "missing"
                    ),
                    reason=(
                        None
                        if player.team is not None
                        else "ESPN did not provide a defense team."
                    ),
                )
            )
            continue

        if model_position == "K" and player.team is not None:
            matched_kicker = match_espn_player(
                id_map=id_map,
                espn_id=player.espn_id,
                espn_name=player.player_name,
                position="K",
            )

            if matched_kicker.status != "matched":
                matched_kicker = ESPNPlayerMatch(
                    espn_id=player.espn_id,
                    espn_name=player.player_name,
                    position="K",
                    player_id=f"TEAM:{player.team}",
                    status="matched",
                )

            player_matches.append(matched_kicker)
            continue

        if model_position not in SUPPORTED_POSITIONS:
            player_matches.append(
                ESPNPlayerMatch(
                    espn_id=player.espn_id,
                    espn_name=player.player_name,
                    position=player.position,
                    player_id=None,
                    status="missing",
                    reason=(
                        "AI projections are not supported "
                        f"for {player.position} yet."
                    ),
                )
            )
            continue

        player_matches.append(
            match_espn_player(
                id_map=id_map,
                espn_id=player.espn_id,
                espn_name=player.player_name,
                position=model_position,
            )
        )

    inactive_qb_espn_ids: set[int] = set()
    player_teams = {
        str(row.player_id): str(row.team).upper()
        for row in roster_df[
            ["player_id", "team"]
        ].itertuples(index=False)
    }
    qb_depth_teams: set[str] = set()

    def mark_inactive_qb(
        index: int,
        player_match: ESPNPlayerMatch,
        team: str,
    ) -> None:
        inactive_qb_espn_ids.add(
            roster_players[index].espn_id
        )
        player_matches[index] = replace(
            player_match,
            status="missing",
            reason=(
                "Player is not the active starting "
                f"quarterback for {team} in week {week}."
            ),
        )

    if depth_chart_df is not None and not depth_chart_df.empty:
        unavailable_player_ids = {
            player_match.player_id
            for roster_player, player_match in zip(
                roster_players,
                player_matches,
            )
            if (
                player_match.player_id is not None
                and roster_player.position == "QB"
                and is_unavailable_injury_status(
                    roster_player.injury_status
                )
            )
        }
        eligible_roster_df = roster_df[
            ~roster_df["player_id"].isin(
                unavailable_player_ids
            )
        ].copy()
        depth_check_opponents = {
            str(team).upper(): opponents.get(
                str(team).upper(),
                "DEPTH_CHECK",
            )
            for team in eligible_roster_df["team"].unique()
        }
        active_qb_ids = {
            request.player_id
            for request in build_projection_requests(
                roster_df=eligible_roster_df,
                opponents=depth_check_opponents,
                position="QB",
                depth_chart_df=depth_chart_df,
            )
        }
        qb_depth_teams = {
            str(team).upper()
            for team in depth_chart_df.loc[
                depth_chart_df["position"] == "QB",
                "team",
            ]
        }
        for index, (roster_player, player_match) in enumerate(
            zip(roster_players, player_matches)
        ):
            player_id = player_match.player_id
            team = (
                player_teams.get(player_id)
                if player_id is not None
                else None
            )
            if (
                roster_player.position == "QB"
                and player_match.status == "matched"
                and player_id not in active_qb_ids
                and team in qb_depth_teams
            ):
                mark_inactive_qb(
                    index=index,
                    player_match=player_match,
                    team=team,
                )

    if use_espn_qb_starter_signal:
        qb_candidates_by_team: dict[
            str,
            list[tuple[int, ESPNPlayerMatch, float]],
        ] = {}

        for index, (roster_player, player_match) in enumerate(
            zip(roster_players, player_matches)
        ):
            player_id = player_match.player_id
            team = (
                player_teams.get(player_id)
                if player_id is not None
                else None
            )
            espn_projection = (
                roster_player.espn_projected_points
            )
            if (
                roster_player.position != "QB"
                or player_match.status != "matched"
                or team is None
                or team in qb_depth_teams
                or espn_projection is None
            ):
                continue

            qb_candidates_by_team.setdefault(
                team,
                [],
            ).append(
                (index, player_match, espn_projection)
            )

        for team, candidates in qb_candidates_by_team.items():
            starter = max(
                candidates,
                key=lambda candidate: candidate[2],
            )
            if starter[2] <= 0:
                continue

            for index, player_match, _ in candidates:
                if index != starter[0]:
                    mark_inactive_qb(
                        index=index,
                        player_match=player_match,
                        team=team,
                    )

    requests_by_position, request_skips = (
        build_espn_request_batches(
            player_matches=player_matches,
            roster_df=roster_df,
            opponents=opponents,
            season=season,
            week=week,
        )
    )

    unavailable_players = [
        {
            "player_id": player_match.player_id,
            "team": roster_player.team,
        }
        for roster_player, player_match in zip(
            roster_players,
            player_matches,
        )
        if (
            roster_player.team is not None
            and roster_player.position in {"QB", "RB", "WR", "TE"}
            and player_match.player_id is not None
            and not player_match.player_id.startswith("TEAM:")
            and is_unavailable_injury_status(
                roster_player.injury_status
            )
        )
    ]
    context_by_team = (
        build_live_team_injury_context(
            player_df=weekly_service.player_df,
            unavailable_players=unavailable_players,
            season=season,
            week=week,
        )
        if unavailable_players
        else {}
    )

    for position, requests in requests_by_position.items():
        if position in {"K", "DST"}:
            continue

        requests_by_position[position] = [
            replace(
                request,
                **{
                    column: context_by_team.get(
                        request.team or "",
                        empty_injury_context(),
                    )[column]
                    for column in TEAMMATE_INJURY_FEATURE_COLS
                },
            )
            for request in requests
        ]

    batch_results = project_espn_request_batches(
        weekly_service=weekly_service,
        requests_by_position=requests_by_position,
    )

    requests_by_player_id = {
        request.player_id: request
        for requests in requests_by_position.values()
        for request in requests
    }

    projections_by_player_id = {
        projection.request.player_id: projection
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

        player_projection = (
            projections_by_player_id.get(player_id)
            if player_id is not None
            else None
        )
        predicted_points = (
            player_projection.predicted_points
            if player_projection is not None
            else None
        )

        is_inactive_qb = (
            roster_player.espn_id
            in inactive_qb_espn_ids
        )
        if is_inactive_qb:
            predicted_points = 0.0

        resolved_team = (
            request.team
            if request is not None
            else roster_player.team
        )
        opponent_team = (
            request.opponent_team
            if request is not None
            else opponents.get(resolved_team or "")
        )
        is_on_bye = (
            bool(opponents)
            and resolved_team in NFL_TEAM_CODES
            and resolved_team not in opponents
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

        if is_on_bye:
            predicted_points = 0.0
            reason = (
                f"{resolved_team} is on bye in week {week}."
            )

        projections.append(
            ESPNRosterProjection(
                espn_id=roster_player.espn_id,
                player_id=player_id,
                player_name=roster_player.player_name,
                position=roster_player.position,
                lineup_slot=roster_player.lineup_slot,
                team=resolved_team,
                opponent_team=opponent_team,
                predicted_points=predicted_points,
                status=(
                    "projected"
                    if (
                        player_projection is not None
                        and not is_inactive_qb
                    )
                    else "skipped"
                ),
                projection_method=(
                    player_projection.projection_method
                    if player_projection is not None
                    else None
                ),
                history_games=(
                    player_projection.history_games
                    if player_projection is not None
                    else None
                ),
                injury_context_used=(
                    player_projection.injury_context_used
                    if player_projection is not None
                    else False
                ),
                unavailable_teammates=(
                    player_projection.unavailable_teammates
                    if player_projection is not None
                    else 0
                ),
                is_on_bye=is_on_bye,
                reason=reason,
            )
        )

    return projections
