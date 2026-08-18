from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from app.services.NFL_data import NFLData

router = APIRouter(prefix="/api/weeks", tags=["weeks"])

@lru_cache(maxsize=3)
def get_schedule_data(season: Annotated[int, Path(ge=2020, le=date.today().year)]) -> NFLData:
    nfl_data = NFLData([season])
    nfl_data.load_data()
    return nfl_data

@router.get("/{season}")
def get_weeks_by_season(
    season: Annotated[
        int, Path(ge=2020, le=date.today().year)
    ]
):
    nfl_data = get_schedule_data(season)

    weeks = []

    for week in range(1, 19):
        games = nfl_data.get_week_schedule(
            season=season,
            week=week,
        )

        if games.empty:
            continue

        weeks.append(
            {
                "week": week,
                "game_count": len(games),
            }
        )

    return {
        "season": season,
        "count": len(weeks),
        "weeks": weeks,
    }

@router.get("/{season}/{week}")
def get_week_schedule(
    season: Annotated[
        int,
        Path(ge=2020, le=date.today().year),
    ],
    week: Annotated[
        int,
        Path(ge=1, le=18),
    ],
):
    nfl_data = get_schedule_data(season)

    games_df = nfl_data.get_week_schedule(
        season=season,
        week=week,
    )

    if games_df.empty:
        raise HTTPException(
            status_code=404,
            detail="No games found for this week",
        )

    games = [
        {
            "away_team": str(game.away_team),
            "home_team": str(game.home_team),
        }
        for game in games_df.itertuples(
            index=False
        )
    ]

    return {
        "season": season,
        "week": week,
        "game_count": len(games),
        "games": games,
    }