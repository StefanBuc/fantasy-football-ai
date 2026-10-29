from bisect import bisect_left

import numpy as np
import pandas as pd

from app.config.model_config import (
    TEAMMATE_INJURY_FEATURE_COLS,
)

UNAVAILABLE_INJURY_STATUSES = {
    "OUT",
    "IR",
    "INJURY_RESERVE",
    "INJURED_RESERVE",
    "PUP",
    "NFI",
    "SUSPENDED",
    "SUSPENSION",
}

USAGE_COLUMNS = [
    "target_share",
    "carries",
    "offense_pct",
]


def normalize_injury_status(value) -> str | None:
    if value is None or pd.isna(value):
        return None

    normalized = str(value).strip().upper().replace(" ", "_")
    return normalized or None


def is_unavailable_injury_status(value) -> bool:
    return normalize_injury_status(value) in (
        UNAVAILABLE_INJURY_STATUSES
    )


def empty_injury_context() -> dict[str, float]:
    return {
        column: 0.0
        for column in TEAMMATE_INJURY_FEATURE_COLS
    }


def _history_by_player(
    player_df: pd.DataFrame,
) -> dict[
    str,
    tuple[list[tuple[int, int]], list[dict[str, float]]],
]:
    required = {
        "player_id",
        "season",
        "week",
        *USAGE_COLUMNS,
    }
    missing = required - set(player_df.columns)
    if missing:
        raise ValueError(
            "Player data is missing injury-context columns: "
            f"{sorted(missing)}"
        )

    source = player_df.copy()
    if "season_type" in source.columns:
        source = source[source["season_type"] == "REG"].copy()

    source[USAGE_COLUMNS] = (
        source[USAGE_COLUMNS]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .astype(float)
    )

    histories = {}
    for player_id, history in source.groupby(
        "player_id",
        sort=False,
    ):
        history = history.sort_values(["season", "week"])
        keys = [
            (int(season), int(week))
            for season, week in zip(
                history["season"],
                history["week"],
            )
        ]
        records = history[USAGE_COLUMNS].to_dict(
            orient="records"
        )
        histories[str(player_id)] = (keys, records)

    return histories


def _recent_usage_before(
    histories: dict[
        str,
        tuple[list[tuple[int, int]], list[dict[str, float]]],
    ],
    player_id: str,
    season: int,
    week: int,
    window: int = 5,
) -> dict[str, float]:
    stored = histories.get(player_id)
    if stored is None:
        return {column: 0.0 for column in USAGE_COLUMNS}

    keys, records = stored
    end = bisect_left(keys, (season, week))
    start = max(0, end - window)
    recent = records[start:end]

    if not recent:
        return {column: 0.0 for column in USAGE_COLUMNS}

    return {
        column: float(
            np.mean([record[column] for record in recent])
        )
        for column in USAGE_COLUMNS
    }


def build_live_team_injury_context(
    player_df: pd.DataFrame,
    unavailable_players: list[dict[str, object]],
    season: int,
    week: int,
) -> dict[str, dict[str, float]]:
    histories = _history_by_player(player_df)
    context_by_team: dict[str, dict[str, float]] = {}

    for player in unavailable_players:
        player_id = str(player["player_id"])
        team = str(player["team"]).upper()
        usage = _recent_usage_before(
            histories=histories,
            player_id=player_id,
            season=season,
            week=week,
        )
        context = context_by_team.setdefault(
            team,
            empty_injury_context(),
        )
        context["teammate_out_count"] += 1.0
        context["teammate_out_target_share"] += usage[
            "target_share"
        ]
        context["teammate_out_carries"] += usage["carries"]
        context["teammate_out_offense_pct"] += usage[
            "offense_pct"
        ]

    return context_by_team


def build_historical_team_injury_context(
    player_df: pd.DataFrame,
    injury_df: pd.DataFrame | None,
) -> pd.DataFrame:
    output_columns = [
        "recent_team",
        "season",
        "week",
        *TEAMMATE_INJURY_FEATURE_COLS,
    ]
    if injury_df is None or injury_df.empty:
        return pd.DataFrame(columns=output_columns)

    required = {
        "season",
        "week",
        "team",
        "gsis_id",
        "position",
        "report_status",
    }
    missing = required - set(injury_df.columns)
    if missing:
        raise ValueError(
            "Injury data is missing columns: "
            f"{sorted(missing)}"
        )

    injuries = injury_df.copy()
    if "game_type" in injuries.columns:
        injuries = injuries[
            injuries["game_type"] == "REG"
        ].copy()
    if "date_modified" in injuries.columns:
        injuries = (
            injuries
            .sort_values("date_modified")
            .drop_duplicates(
                subset=["season", "week", "team", "gsis_id"],
                keep="last",
            )
        )

    injuries = injuries[
        injuries["report_status"].map(
            is_unavailable_injury_status
        )
        & injuries["position"].isin(
            ["QB", "RB", "WR", "TE"]
        )
        & injuries["gsis_id"].notna()
    ].copy()

    unavailable_players = [
        {
            "player_id": str(row.gsis_id),
            "team": str(row.team).upper(),
            "season": int(row.season),
            "week": int(row.week),
        }
        for row in injuries.itertuples(index=False)
    ]
    histories = _history_by_player(player_df)
    rows = []

    for player in unavailable_players:
        usage = _recent_usage_before(
            histories=histories,
            player_id=str(player["player_id"]),
            season=int(player["season"]),
            week=int(player["week"]),
        )
        rows.append(
            {
                "recent_team": str(player["team"]),
                "season": int(player["season"]),
                "week": int(player["week"]),
                "teammate_out_count": 1.0,
                "teammate_out_target_share": usage[
                    "target_share"
                ],
                "teammate_out_carries": usage["carries"],
                "teammate_out_offense_pct": usage[
                    "offense_pct"
                ],
            }
        )

    if not rows:
        return pd.DataFrame(columns=output_columns)

    return (
        pd.DataFrame(rows)
        .groupby(
            ["recent_team", "season", "week"],
            as_index=False,
        )[TEAMMATE_INJURY_FEATURE_COLS]
        .sum()
    )
