from dataclasses import dataclass
from typing import Literal

import pandas as pd


MatchStatus = Literal[
    "matched",
    "missing",
    "ambiguous",
]


@dataclass(frozen=True)
class ESPNPlayerMatch:
    espn_id: int
    espn_name: str
    position: str
    player_id: str | None
    status: MatchStatus
    reason: str | None = None


def match_espn_player(
    id_map: pd.DataFrame,
    espn_id: int,
    espn_name: str,
    position: str,
) -> ESPNPlayerMatch:
    required_columns = {
        "espn_id",
        "player_id",
        "position",
    }

    missing_columns = (
        required_columns - set(id_map.columns)
    )

    if missing_columns:
        raise ValueError(
            f"ID map is missing columns: "
            f"{sorted(missing_columns)}"
        )

    candidates = id_map[
        id_map["espn_id"] == espn_id
    ].copy()

    if candidates.empty:
        return ESPNPlayerMatch(
            espn_id=espn_id,
            espn_name=espn_name,
            position=position,
            player_id=None,
            status="missing",
            reason="No NFL player ID mapping was found.",
        )

    if len(candidates) > 1:
        position_candidates = candidates[
            candidates["position"]
            .map(lambda value: str(value).upper())
            == position.upper()
        ].copy()

        if len(position_candidates) == 1:
            candidates = position_candidates

    if len(candidates) != 1:
        return ESPNPlayerMatch(
            espn_id=espn_id,
            espn_name=espn_name,
            position=position,
            player_id=None,
            status="ambiguous",
            reason=(
                f"Found {len(candidates)} possible "
                "NFL player ID mappings."
            ),
        )

    player_id = str(
        candidates.iloc[0]["player_id"]
    )

    return ESPNPlayerMatch(
        espn_id=espn_id,
        espn_name=espn_name,
        position=position,
        player_id=player_id,
        status="matched",
    )