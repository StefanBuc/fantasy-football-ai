from collections.abc import Iterable

import nfl_data_py as nfl
import numpy as np
import pandas as pd


PBP_COLUMNS = [
    "game_id",
    "season_type",
    "week",
    "home_team",
    "away_team",
    "posteam",
    "defteam",
    "play_type",
    "touchdown",
    "td_team",
    "interception",
    "fumble_lost",
    "sack",
    "safety",
    "return_touchdown",
    "extra_point_result",
    "field_goal_result",
    "kick_distance",
    "kicker_player_id",
    "kicker_player_name",
    "total_home_score",
    "total_away_score",
    "yards_gained",
    "punt_blocked",
]


def load_play_by_play(seasons: Iterable[int]) -> pd.DataFrame:
    return nfl.import_pbp_data(
        sorted(set(seasons)),
        columns=PBP_COLUMNS,
        include_participation=False,
        downcast=True,
    )


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def score_kicker_week(
    field_goals_0_39: float,
    field_goals_40_49: float,
    field_goals_50_59: float,
    field_goals_60_plus: float,
    field_goals_missed: float,
    extra_points_made: float,
) -> float:
    return float(
        (field_goals_0_39 * 3)
        + (field_goals_40_49 * 4)
        + (field_goals_50_59 * 5)
        + (field_goals_60_plus * 6)
        - field_goals_missed
        + extra_points_made
    )


def score_dst_week(
    sacks: float,
    interceptions: float,
    fumble_recoveries: float,
    blocked_kicks: float,
    safeties: float,
    return_touchdowns: float,
    points_allowed: float,
    yards_allowed: float,
) -> float:
    if points_allowed == 0:
        points_score = 5
    elif points_allowed <= 6:
        points_score = 4
    elif points_allowed <= 13:
        points_score = 3
    elif points_allowed <= 17:
        points_score = 1
    elif points_allowed <= 27:
        points_score = 0
    elif points_allowed <= 34:
        points_score = -1
    elif points_allowed <= 45:
        points_score = -3
    else:
        points_score = -5

    if yards_allowed < 100:
        yards_score = 5
    elif yards_allowed < 200:
        yards_score = 3
    elif yards_allowed < 300:
        yards_score = 2
    elif yards_allowed < 350:
        yards_score = 0
    elif yards_allowed < 400:
        yards_score = -1
    elif yards_allowed < 450:
        yards_score = -3
    elif yards_allowed < 500:
        yards_score = -5
    elif yards_allowed < 550:
        yards_score = -6
    else:
        yards_score = -7

    return float(
        sacks
        + (interceptions * 2)
        + (fumble_recoveries * 2)
        + (blocked_kicks * 2)
        + (safeties * 2)
        + (return_touchdowns * 6)
        + points_score
        + yards_score
    )


def build_kicker_weekly(pbp: pd.DataFrame) -> pd.DataFrame:
    plays = pbp[pbp["season_type"] == "REG"].copy()
    kicks = plays[
        plays["play_type"].isin(["field_goal", "extra_point"])
        & plays["kicker_player_id"].notna()
        & plays["posteam"].notna()
        & plays["defteam"].notna()
    ].copy()

    if kicks.empty:
        return pd.DataFrame()

    kick_distance = _number(kicks["kick_distance"])
    is_field_goal = kicks["play_type"] == "field_goal"
    field_goal_made = is_field_goal & (kicks["field_goal_result"] == "made")

    kicks["field_goals_attempted"] = is_field_goal.astype(float)
    kicks["field_goals_made"] = field_goal_made.astype(float)
    kicks["field_goals_missed"] = (
        is_field_goal & ~field_goal_made
    ).astype(float)
    kicks["field_goals_0_39"] = (
        field_goal_made & (kick_distance < 40)
    ).astype(float)
    kicks["field_goals_40_49"] = (
        field_goal_made
        & (kick_distance >= 40)
        & (kick_distance < 50)
    ).astype(float)
    kicks["field_goals_50_59"] = (
        field_goal_made
        & (kick_distance >= 50)
        & (kick_distance < 60)
    ).astype(float)
    kicks["field_goals_60_plus"] = (
        field_goal_made & (kick_distance >= 60)
    ).astype(float)
    kicks["extra_points_attempted"] = (
        kicks["play_type"] == "extra_point"
    ).astype(float)
    kicks["extra_points_made"] = (
        (kicks["play_type"] == "extra_point")
        & (kicks["extra_point_result"] == "good")
    ).astype(float)

    stat_columns = [
        "field_goals_attempted",
        "field_goals_made",
        "field_goals_missed",
        "field_goals_0_39",
        "field_goals_40_49",
        "field_goals_50_59",
        "field_goals_60_plus",
        "extra_points_attempted",
        "extra_points_made",
    ]

    weekly = (
        kicks.groupby(
            [
                "season",
                "week",
                "kicker_player_id",
                "kicker_player_name",
                "posteam",
                "defteam",
            ],
            dropna=False,
        )[stat_columns]
        .sum()
        .reset_index()
        .rename(
            columns={
                "kicker_player_id": "entity_id",
                "kicker_player_name": "entity_name",
                "posteam": "team",
                "defteam": "opponent_team",
            }
        )
    )

    weekly["position"] = "K"
    weekly["fantasy_points"] = weekly.apply(
        lambda row: score_kicker_week(
            field_goals_0_39=row["field_goals_0_39"],
            field_goals_40_49=row["field_goals_40_49"],
            field_goals_50_59=row["field_goals_50_59"],
            field_goals_60_plus=row["field_goals_60_plus"],
            field_goals_missed=row["field_goals_missed"],
            extra_points_made=row["extra_points_made"],
        ),
        axis=1,
    )

    return weekly.sort_values(
        ["entity_id", "season", "week"]
    ).reset_index(drop=True)


def build_dst_weekly(pbp: pd.DataFrame) -> pd.DataFrame:
    plays = pbp[
        (pbp["season_type"] == "REG")
        & pbp["game_id"].notna()
    ].copy()

    if plays.empty:
        return pd.DataFrame()

    game_rows = []

    for game_id, game in plays.groupby("game_id", sort=False):
        first = game.iloc[0]
        home_team = str(first["home_team"])
        away_team = str(first["away_team"])
        season = int(first["season"])
        week = int(first["week"])
        home_score = float(_number(game["total_home_score"]).max())
        away_score = float(_number(game["total_away_score"]).max())

        for team, opponent, points_allowed in (
            (home_team, away_team, away_score),
            (away_team, home_team, home_score),
        ):
            defensive_plays = game[game["defteam"] == team]
            opponent_offense = game[
                (game["posteam"] == opponent)
                & game["play_type"].isin(["pass", "run"])
            ]

            sacks = float(_number(defensive_plays["sack"]).sum())
            interceptions = float(
                _number(defensive_plays["interception"]).sum()
            )
            fumble_recoveries = float(
                _number(defensive_plays["fumble_lost"]).sum()
            )
            safeties = float(_number(defensive_plays["safety"]).sum())
            blocked_kicks = float(
                (
                    _number(defensive_plays["punt_blocked"]) > 0
                ).sum()
                + (
                    defensive_plays["field_goal_result"] == "blocked"
                ).sum()
                + (
                    defensive_plays["extra_point_result"] == "blocked"
                ).sum()
            )
            return_touchdowns = float(
                (
                    (_number(game["return_touchdown"]) > 0)
                    & (game["td_team"] == team)
                ).sum()
            )
            yards_allowed = float(
                _number(opponent_offense["yards_gained"]).sum()
            )

            game_rows.append(
                {
                    "game_id": game_id,
                    "season": season,
                    "week": week,
                    "entity_id": team,
                    "entity_name": f"{team} D/ST",
                    "position": "DST",
                    "team": team,
                    "opponent_team": opponent,
                    "sacks": sacks,
                    "interceptions": interceptions,
                    "fumble_recoveries": fumble_recoveries,
                    "blocked_kicks": blocked_kicks,
                    "safeties": safeties,
                    "return_touchdowns": return_touchdowns,
                    "points_allowed": points_allowed,
                    "yards_allowed": yards_allowed,
                }
            )

    weekly = pd.DataFrame(game_rows)
    weekly["fantasy_points"] = weekly.apply(
        lambda row: score_dst_week(
            sacks=row["sacks"],
            interceptions=row["interceptions"],
            fumble_recoveries=row["fumble_recoveries"],
            blocked_kicks=row["blocked_kicks"],
            safeties=row["safeties"],
            return_touchdowns=row["return_touchdowns"],
            points_allowed=row["points_allowed"],
            yards_allowed=row["yards_allowed"],
        ),
        axis=1,
    )

    return weekly.sort_values(
        ["entity_id", "season", "week"]
    ).reset_index(drop=True)


def load_special_teams_weekly(
    seasons: Iterable[int],
) -> dict[str, pd.DataFrame]:
    pbp = load_play_by_play(seasons)

    if pbp.empty:
        raise ValueError(
            "No play-by-play data was available for the requested seasons."
        )

    return {
        "K": build_kicker_weekly(pbp),
        "DST": build_dst_weekly(pbp),
    }
