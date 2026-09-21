from functools import lru_cache

from fastapi import APIRouter, HTTPException
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
    ESPNInvalidLeague,
    ESPNUnknownError,
)

from app.integrations.espn_fantasy import get_league
from app.integrations.espn_roster_projection import (
    ESPNRosterPlayer,
    project_espn_roster,
)
from app.schemas.espn import (
    ESPNLeagueConnectRequest,
    ESPNLeagueConnectResponse,
    ESPNRosterProjectionResponse,
    ESPNTeamSummary,
    ESPNTeamProjectionRequest,
    ESPNTeamProjectionResponse,
)
from app.services.weekly_projection_service import (
    WeeklyProjectionService,
)


router = APIRouter(prefix="/api/espn", tags=["espn"])

SUPPORTED_POSITIONS = {
    "QB",
    "RB",
    "WR",
    "TE",
}


@lru_cache(maxsize=2)
def get_espn_projection_service(
    season: int,
) -> WeeklyProjectionService:
    return WeeklyProjectionService(season=season)


def get_public_league(
    league_id: int,
    season: int,
):
    try:
        return get_league(
            league_id=league_id,
            year=season,
        )

    except ESPNAccessDenied as error:
        raise HTTPException(
            status_code=403,
            detail=(
                "This league is private or ESPN "
                "denied access."
            ),
        ) from error

    except ESPNInvalidLeague as error:
        raise HTTPException(
            status_code=404,
            detail="ESPN league not found.",
        ) from error

    except ESPNUnknownError as error:
        raise HTTPException(
            status_code=502,
            detail="ESPN returned an unexpected response.",
        ) from error


def find_league_team(league, team_id: int):
    team = next(
        (
            team
            for team in league.teams
            if int(team.team_id) == team_id
        ),
        None,
    )

    if team is None:
        raise HTTPException(
            status_code=404,
            detail=f"ESPN team {team_id} was not found.",
        )

    return team


@router.post("/connect", response_model=ESPNLeagueConnectResponse)
def connect_public_league(
    payload: ESPNLeagueConnectRequest,
) -> ESPNLeagueConnectResponse:
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )

    teams = [
        ESPNTeamSummary(
            team_id=int(team.team_id),
            team_name=str(team.team_name),
            abbreviation=str(team.team_abbrev),
            logo_url=(
                str(team.logo_url)
                if team.logo_url
                else None
            ),
        )
        for team in league.teams
    ]

    return ESPNLeagueConnectResponse(
        league_id=payload.league_id,
        season=payload.season,
        league_name=str(league.settings.name),
        team_count=len(teams),
        teams=teams,
    )


@router.post(
    "/projections",
    response_model=ESPNTeamProjectionResponse,
)
def get_public_team_projections(
    payload: ESPNTeamProjectionRequest,
) -> ESPNTeamProjectionResponse:
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )
    team = find_league_team(
        league=league,
        team_id=payload.team_id,
    )

    roster_players = [
        ESPNRosterPlayer(
            espn_id=int(player.playerId),
            player_name=str(player.name),
            position=str(player.position).upper(),
            lineup_slot=str(player.lineupSlot),
        )
        for player in team.roster
        if str(player.position).upper()
        in SUPPORTED_POSITIONS
    ]

    try:
        service = get_espn_projection_service(
            season=payload.season
        )
        roster_df = service.data.get_week_roster(
            season=payload.season,
            week=payload.week,
        )
        opponents = service.data.get_week_opponents(
            season=payload.season,
            week=payload.week,
        )
        id_map = service.data.get_player_id_map()

        projections = project_espn_roster(
            weekly_service=service,
            roster_players=roster_players,
            id_map=id_map,
            roster_df=roster_df,
            opponents=opponents,
            season=payload.season,
            week=payload.week,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    players = [
        ESPNRosterProjectionResponse(
            espn_id=item.espn_id,
            player_id=item.player_id,
            player_name=item.player_name,
            position=item.position,
            lineup_slot=item.lineup_slot,
            team=item.team,
            opponent_team=item.opponent_team,
            predicted_points=item.predicted_points,
            status=item.status,
            reason=item.reason,
        )
        for item in projections
    ]

    projected_count = sum(
        player.status == "projected"
        for player in players
    )

    return ESPNTeamProjectionResponse(
        league_id=payload.league_id,
        league_name=str(league.settings.name),
        season=payload.season,
        week=payload.week,
        team_id=payload.team_id,
        team_name=str(team.team_name),
        projected_count=projected_count,
        skipped_count=len(players) - projected_count,
        players=players,
    )
