from fastapi import APIRouter, HTTPException
from app.services.NFL_data import NFLData
from functools import lru_cache
import pandas as pd
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from app.schemas.predictions import Position

router = APIRouter(prefix="/api/players", tags=["players"])

@lru_cache(maxsize=1)
def get_nfl_data() -> NFLData:
    nfl_data = NFLData()
    nfl_data.load_data()
    return nfl_data

@router.get("/")
def get_players():
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()

    players = (
        players_df
        .sort_values(["season", "week"])
        .drop_duplicates(
            subset=["player_id"],
            keep="last",
        )
        [
            [
                "player_id",
                "player_name",
                "position",
                "recent_team",
            ]
        ]
        .rename(
            columns={"recent_team": "team"}
        )
        .reset_index(drop=True)
    )

    clean_players = (
        players
        .astype(object)
        .where(pd.notna(players), None)
    )

    return {
        "count": len(clean_players),
        "players": clean_players.to_dict(
            orient="records"
        ),
    }

@router.get("/{player_id}")
def get_player(player_id: str):
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()
    player_rows = players_df[
        players_df["player_id"] == player_id
    ].copy()

    if player_rows.empty:
        raise HTTPException(
            status_code=404,
            detail="Player not found",
        )

    latest_row = (
        player_rows
        .sort_values(["season", "week"])
        .iloc[-1]
    )

    return {
        "player": {
            "player_id": str(latest_row["player_id"]),
            "player_name": str(latest_row["player_name"]),
            "position": str(latest_row["position"]),
            "team": str(latest_row["recent_team"]),
        }
    }

@router.get("/{player_id}/stats")
def get_player_stats(player_id: str):
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()
    player_rows = players_df[players_df["player_id"] == player_id].copy()

    if player_rows.empty:
        raise HTTPException(
            status_code=404,
            detail="Player stats not found",
        )

    player_rows = (
        player_rows
        .sort_values(["season", "week"])
        .reset_index(drop=True)
    )

    clean_rows = (
        player_rows
        .astype(object)
        .where(pd.notna(player_rows), None)
    )

    return {
        "player_stats": clean_rows.to_dict(
            orient="records"
        )
    }

@router.get("/{season}/{position}")
def get_players_by_season_and_position(season: Annotated[int, Path(ge=2020, le=date.today().year)], position: Position):
    nfl_data = get_nfl_data()
    players_df = nfl_data.get_player_stats()

    filtered_players = players_df[
        (players_df["season"] == season)
        & (players_df["position"] == position)
    ].copy()

    if filtered_players.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                "No players found for the given "
                "season and position"
            ),
        )

    players = (
        filtered_players
        .sort_values(["season", "week"])
        .drop_duplicates(
            subset=["player_id"],
            keep="last",
        )
        [
            [
                "player_id",
                "player_name",
                "position",
                "recent_team",
            ]
        ]
        .rename(
            columns={"recent_team": "team"}
        )
        .reset_index(drop=True)
    )

    clean_players = (
        players
        .astype(object)
        .where(pd.notna(players), None)
    )

    return {
        "season": season,
        "position": position,
        "count": len(clean_players),
        "players": clean_players.to_dict(
            orient="records"
        ),
    }