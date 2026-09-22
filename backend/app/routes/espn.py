from functools import lru_cache
from typing import Any, Literal
from urllib.parse import urlparse

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request, Response
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
    ESPNInvalidLeague,
    ESPNUnknownError,
)

from app.config.espn_config import (
    ESPNLocalConfig,
    get_local_espn_config,
    local_espn_api_enabled,
)
from app.integrations.espn_fantasy import get_league
from app.schemas.espn import (
    ESPNLeagueConnectRequest,
    ESPNLeagueConnectResponse,
    ESPNLocalTeamProjectionRequest,
    ESPNMatchupResponse,
    ESPNRosterProjectionResponse,
    ESPNTeamSummary,
    ESPNTeamProjectionRequest,
    ESPNTeamProjectionResponse,
)
from app.services.weekly_projection_service import (
    WeeklyProjectionService,
)
from app.services.espn_projection_cache import (
    ESPNProjectionCache,
    build_league_week_projection,
    roster_fingerprint,
)


router = APIRouter(prefix="/api/espn", tags=["espn"])

LOCAL_CLIENT_HOSTS = {
    "127.0.0.1",
    "::1",
    "testclient",
}

ESPN_TEAM_ALIASES = {
    "LAR": "LA",
    "WSH": "WAS",
}

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

projection_cache = ESPNProjectionCache()


def normalize_espn_team(team: str) -> str:
    normalized = team.upper()
    return ESPN_TEAM_ALIASES.get(
        normalized,
        normalized,
    )


def normalize_injury_status(
    injury_status: Any,
) -> str | None:
    if injury_status is None:
        return None

    normalized = str(injury_status).strip().upper()
    return normalized or None


def classify_availability(
    injury_status: str | None,
) -> Literal[
    "healthy",
    "questionable",
    "doubtful",
    "unavailable",
    "unknown",
]:
    if injury_status is None or injury_status in {
        "ACTIVE",
        "HEALTHY",
        "NORMAL",
    }:
        return "healthy"
    if injury_status == "QUESTIONABLE":
        return "questionable"
    if injury_status == "DOUBTFUL":
        return "doubtful"
    if injury_status in UNAVAILABLE_INJURY_STATUSES:
        return "unavailable"
    return "unknown"


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


def require_local_espn_access(
    request: Request,
) -> ESPNLocalConfig:
    client_host = (
        request.client.host
        if request.client is not None
        else None
    )

    if (
        not local_espn_api_enabled()
        or client_host not in LOCAL_CLIENT_HOSTS
    ):
        raise HTTPException(
            status_code=404,
            detail="Local ESPN access is disabled.",
        )

    try:
        return get_local_espn_config()
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error


def get_configured_private_league(
    request: Request,
) -> tuple[ESPNLocalConfig, Any]:
    config = require_local_espn_access(request)

    try:
        league = get_league(
            league_id=config.league_id,
            year=config.season,
            espn_s2=config.espn_s2,
            swid=config.swid,
        )
    except ESPNAccessDenied as error:
        raise HTTPException(
            status_code=403,
            detail=(
                "The configured ESPN credentials were "
                "not accepted."
            ),
        ) from error
    except ESPNInvalidLeague as error:
        raise HTTPException(
            status_code=404,
            detail="The configured ESPN league was not found.",
        ) from error
    except ESPNUnknownError as error:
        raise HTTPException(
            status_code=502,
            detail="ESPN returned an unexpected response.",
        ) from error

    return config, league


@router.get(
    "/local/team-logo/{team_id}",
    include_in_schema=False,
)
def get_configured_private_team_logo(
    team_id: int,
    request: Request,
) -> Response:
    config, league = get_configured_private_league(request)
    team = find_league_team(league, team_id)
    logo_url = str(getattr(team, "logo_url", ""))
    parsed_url = urlparse(logo_url)

    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname
        != "mystique-api.fantasy.espn.com"
    ):
        raise HTTPException(
            status_code=404,
            detail="This team does not use a protected ESPN logo.",
        )

    try:
        logo_response = http_requests.get(
            logo_url,
            cookies={
                "espn_s2": config.espn_s2,
                "SWID": config.swid,
            },
            timeout=10,
        )
        logo_response.raise_for_status()
    except http_requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="ESPN team logo could not be loaded.",
        ) from error

    content_type = logo_response.headers.get(
        "content-type",
        "",
    )
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=502,
            detail="ESPN returned an invalid team logo.",
        )

    return Response(
        content=logo_response.content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


def build_league_connect_response(
    league,
    league_id: int,
    season: int,
) -> ESPNLeagueConnectResponse:
    current_week = min(
        max(int(getattr(league, "current_week", 1)), 1),
        18,
    )

    ordered_teams = (
        league.standings()
        if callable(getattr(league, "standings", None))
        else league.teams
    )
    standings = {
        int(team.team_id): rank
        for rank, team in enumerate(
            ordered_teams,
            start=1,
        )
    }

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
            standing=standings.get(
                int(team.team_id),
                int(getattr(team, "standing", 0)),
            ),
            wins=int(getattr(team, "wins", 0)),
            losses=int(getattr(team, "losses", 0)),
            ties=int(getattr(team, "ties", 0)),
            points_for=float(getattr(team, "points_for", 0.0)),
            points_against=float(
                getattr(team, "points_against", 0.0)
            ),
            streak=(
                f"{str(team.streak_type)[0]}{int(team.streak_length)}"
                if getattr(team, "streak_type", None)
                and getattr(team, "streak_length", 0)
                else None
            ),
            playoff_pct=(
                float(team.playoff_pct)
                if getattr(team, "playoff_pct", None) is not None
                else None
            ),
        )
        for team in league.teams
    ]

    return ESPNLeagueConnectResponse(
        league_id=league_id,
        season=season,
        current_week=current_week,
        league_name=str(league.settings.name),
        team_count=len(teams),
        teams=teams,
    )


def build_matchup_response(
    league,
    league_id: int,
    season: int,
    team_id: int,
    week: int,
) -> ESPNMatchupResponse:
    matchup = next(
        (
            matchup
            for matchup in league.scoreboard(week)
            if team_id
            in {
                int(matchup.home_team.team_id),
                int(matchup.away_team.team_id),
            }
        ),
        None,
    )

    if matchup is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No ESPN matchup was found for team "
                f"{team_id} in week {week}."
            ),
        )

    home_team_id = int(matchup.home_team.team_id)
    away_team_id = int(matchup.away_team.team_id)

    return ESPNMatchupResponse(
        league_id=league_id,
        league_name=str(league.settings.name),
        season=season,
        week=week,
        home_score=float(matchup.home_score),
        away_score=float(matchup.away_score),
        home=build_team_projection_response(
            league=league,
            league_id=league_id,
            season=season,
            team_id=home_team_id,
            week=week,
        ),
        away=build_team_projection_response(
            league=league,
            league_id=league_id,
            season=season,
            team_id=away_team_id,
            week=week,
        ),
    )


def build_team_projection_response(
    league,
    league_id: int,
    season: int,
    team_id: int,
    week: int,
) -> ESPNTeamProjectionResponse:
    team = find_league_team(
        league=league,
        team_id=team_id,
    )

    try:
        service = get_espn_projection_service(
            season=season
        )
        cache_key = (
            league_id,
            season,
            week,
            roster_fingerprint(league),
        )
        cached_projection, cache_hit = (
            projection_cache.get_or_create(
                key=cache_key,
                builder=lambda: build_league_week_projection(
                    league=league,
                    service=service,
                    season=season,
                    week=week,
                    normalize_team=normalize_espn_team,
                ),
            )
        )
        projections = cached_projection.team_projections.get(
            team_id,
            (),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    current_players = {
        int(player.playerId): player
        for player in team.roster
    }
    players = []

    for item in projections:
        current_player = current_players.get(item.espn_id)
        injury_status = normalize_injury_status(
            getattr(current_player, "injuryStatus", None)
        )
        availability = classify_availability(injury_status)
        predicted_points = item.predicted_points
        adjustment_reason = None

        if (
            availability == "unavailable"
            and predicted_points is not None
        ):
            predicted_points = 0.0
            adjustment_reason = (
                f"ESPN lists this player as {injury_status}."
            )

        players.append(
            ESPNRosterProjectionResponse(
                espn_id=item.espn_id,
                player_id=item.player_id,
                player_name=item.player_name,
                position=item.position,
                lineup_slot=item.lineup_slot,
                team=item.team,
                opponent_team=item.opponent_team,
                base_predicted_points=item.predicted_points,
                predicted_points=predicted_points,
                status=item.status,
                injury_status=injury_status,
                availability=availability,
                adjustment_reason=adjustment_reason,
                reason=item.reason,
            )
        )

    projected_count = sum(
        player.status == "projected"
        for player in players
    )

    return ESPNTeamProjectionResponse(
        league_id=league_id,
        league_name=str(league.settings.name),
        season=season,
        week=week,
        roster_week=cached_projection.roster_week,
        team_id=team_id,
        team_name=str(team.team_name),
        generated_at=cached_projection.generated_at,
        cache_hit=cache_hit,
        projected_count=projected_count,
        skipped_count=len(players) - projected_count,
        players=players,
    )


@router.post("/connect", response_model=ESPNLeagueConnectResponse)
def connect_public_league(
    payload: ESPNLeagueConnectRequest,
) -> ESPNLeagueConnectResponse:
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )

    return build_league_connect_response(
        league=league,
        league_id=payload.league_id,
        season=payload.season,
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
    return build_team_projection_response(
        league=league,
        league_id=payload.league_id,
        season=payload.season,
        team_id=payload.team_id,
        week=payload.week,
    )


@router.post(
    "/matchup",
    response_model=ESPNMatchupResponse,
)
def get_public_matchup(
    payload: ESPNTeamProjectionRequest,
) -> ESPNMatchupResponse:
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )
    return build_matchup_response(
        league=league,
        league_id=payload.league_id,
        season=payload.season,
        team_id=payload.team_id,
        week=payload.week,
    )
@router.post(
    "/local/connect",
    response_model=ESPNLeagueConnectResponse,
    include_in_schema=False,
)
def connect_configured_private_league(
    request: Request,
) -> ESPNLeagueConnectResponse:
    config, league = get_configured_private_league(
        request
    )

    return build_league_connect_response(
        league=league,
        league_id=config.league_id,
        season=config.season,
    )


@router.post(
    "/local/projections",
    response_model=ESPNTeamProjectionResponse,
    include_in_schema=False,
)
def get_configured_private_team_projections(
    payload: ESPNLocalTeamProjectionRequest,
    request: Request,
) -> ESPNTeamProjectionResponse:
    config, league = get_configured_private_league(
        request
    )

    return build_team_projection_response(
        league=league,
        league_id=config.league_id,
        season=config.season,
        team_id=payload.team_id,
        week=payload.week,
    )


@router.post(
    "/local/matchup",
    response_model=ESPNMatchupResponse,
    include_in_schema=False,
)
def get_configured_private_matchup(
    payload: ESPNLocalTeamProjectionRequest,
    request: Request,
) -> ESPNMatchupResponse:
    config, league = get_configured_private_league(request)
    return build_matchup_response(
        league=league,
        league_id=config.league_id,
        season=config.season,
        team_id=payload.team_id,
        week=payload.week,
    )
