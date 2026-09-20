from dataclasses import dataclass
from typing import Literal

import pandas as pd

from app.integrations.espn_player_matching import (
    ESPNPlayerMatch,
)
from app.services.projection_types import (
    PlayerProjectionRequest,
)


RosterProjectionStatus = Literal[
    "projected",
    "skipped",
]


@dataclass(frozen=True)
class ESPNRosterProjection:
    espn_id: int
    player_id: str
    player_name: str
    position: str
    lineup_slot: str
    team: str | None
    opponent_team: str | None
    predicted_points: float | None
    status: RosterProjectionStatus
    reason: str | None = None
    
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