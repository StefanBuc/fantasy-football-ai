from typing import Any, Literal
from datetime import datetime, timezone
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
from app.integrations.espn_roster_projection import (
    project_espn_roster,
)
from app.schemas.espn import (
    ESPNLeagueConnectRequest,
    ESPNLeagueConnectResponse,
    ESPNLeaguePlayerResponse,
    ESPNLeaguePlayersRequest,
    ESPNLeaguePlayersResponse,
    ESPNLocalLeaguePlayersRequest,
    ESPNLocalTeamProjectionRequest,
    ESPNMatchupResponse,
    ESPNScoreboardMatchup,
    ESPNRosterProjectionResponse,
    ESPNTeamSummary,
    ESPNTeamProjectionRequest,
    ESPNTeamProjectionResponse,
    ESPNLiveRequest,
    ESPNLocalLiveRequest,
    ESPNLiveResponse,
)
from app.services.weekly_projection_service import (
    WeeklyProjectionService,
)
from app.services.projection_registry import projection_services
from app.services.prediction_history import record_predictions
from app.services.accuracy_jobs import register_league_tracking
from app.services.score_presentation import prediction_display
from app.services.live_scores import live_response, LiveLeagueClient
from app.services.matchup_probability import estimate_win_chance
from app.services.espn_connection_cache import espn_connection_cache
from app.services.espn_projection_cache import (
    ESPNProjectionCache,
    build_league_week_projection,
    make_roster_player,
    roster_fingerprint,
)
from app.services.teammate_injury_features import (
    is_unavailable_injury_status,
    normalize_injury_status,
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

projection_cache = ESPNProjectionCache(persistent=True)

PLAYER_POOL_POSITIONS = {
    "QB",
    "RB",
    "WR",
    "TE",
    "K",
    "D/ST",
}

PLAYER_POOL_POSITION_ORDER = {
    position: index
    for index, position in enumerate(
        ("QB", "RB", "WR", "TE", "D/ST", "K")
    )
}


def normalize_espn_team(team: str) -> str:
    normalized = team.upper()
    return ESPN_TEAM_ALIASES.get(
        normalized,
        normalized,
    )


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
    if is_unavailable_injury_status(injury_status):
        return "unavailable"
    return "unknown"


def optional_percentage(value: Any) -> float | None:
    try:
        percentage = float(value)
    except (TypeError, ValueError):
        return None

    return percentage if percentage >= 0 else None


def optional_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def player_pro_team(player) -> str | None:
    raw_team = getattr(player, "proTeam", None)
    if raw_team is None:
        return None

    team = str(raw_team).strip().upper()
    if team in {"", "0", "FA", "NONE"}:
        return None

    return normalize_espn_team(team)


def build_league_player(
    player,
    roster_status: Literal["available", "rostered"],
    fantasy_team_id: int | None = None,
    fantasy_team_name: str | None = None,
) -> ESPNLeaguePlayerResponse | None:
    position = str(
        getattr(player, "position", "")
    ).upper()
    if position not in PLAYER_POOL_POSITIONS:
        return None

    injury_status = normalize_injury_status(
        getattr(player, "injuryStatus", None)
    )

    return ESPNLeaguePlayerResponse(
        espn_id=int(player.playerId),
        player_name=str(player.name),
        position=position,
        team=player_pro_team(player),
        roster_status=roster_status,
        fantasy_team_id=fantasy_team_id,
        fantasy_team_name=fantasy_team_name,
        percent_owned=optional_percentage(
            getattr(player, "percent_owned", None)
        ),
        percent_started=optional_percentage(
            getattr(player, "percent_started", None)
        ),
        season_average=optional_number(
            getattr(player, "avg_points", None)
        ),
        opponent_team=None,
        base_predicted_points=None,
        predicted_points=None,
        projection_status="skipped",
        projection_method=None,
        history_games=None,
        projection_reason="Projection has not been calculated.",
        is_on_bye=False,
        injury_status=injury_status,
        availability=classify_availability(injury_status),
    )


def project_league_players(
    league,
    league_id: int,
    season: int,
    week: int,
    service: WeeklyProjectionService | None = None,
    strict_history: bool = False,
    history_schedule=None,
) -> tuple[ESPNLeaguePlayersResponse, int]:
    players_by_id: dict[int, ESPNLeaguePlayerResponse] = {}
    player_sources_by_id: dict[int, Any] = {}

    for fantasy_team in league.teams:
        fantasy_team_id = int(fantasy_team.team_id)
        fantasy_team_name = str(fantasy_team.team_name)

        for player in fantasy_team.roster:
            league_player = build_league_player(
                player=player,
                roster_status="rostered",
                fantasy_team_id=fantasy_team_id,
                fantasy_team_name=fantasy_team_name,
            )
            if league_player is not None:
                players_by_id[league_player.espn_id] = (
                    league_player
                )
                player_sources_by_id[league_player.espn_id] = (
                    player
                )

    try:
        free_agents = league.free_agents(
            week=week,
            size=1000,
        )
    except ESPNAccessDenied as error:
        raise HTTPException(
            status_code=403,
            detail="ESPN denied access to the player pool.",
        ) from error
    except ESPNUnknownError as error:
        raise HTTPException(
            status_code=502,
            detail="ESPN could not return the player pool.",
        ) from error

    for player in free_agents:
        league_player = build_league_player(
            player=player,
            roster_status="available",
        )
        if (
            league_player is not None
            and league_player.espn_id not in players_by_id
        ):
            players_by_id[league_player.espn_id] = league_player
            player_sources_by_id[league_player.espn_id] = player

    if service is None:
        service = get_espn_projection_service(season)
    roster_df, roster_week = (
        service.data.get_projection_roster(
            season=season,
            week=week,
        )
    )
    opponents = service.data.get_week_opponents(
        season=season,
        week=week,
    )
    id_map = service.data.get_player_id_map()

    roster_players = [
        make_roster_player(
            player=player_sources_by_id[espn_id],
            normalize_team=normalize_espn_team,
            week=week,
        )
        for espn_id in players_by_id
    ]
    pool_projections = project_espn_roster(
        weekly_service=service,
        roster_players=roster_players,
        id_map=id_map,
        roster_df=roster_df,
        opponents=opponents,
        season=season,
        week=week,
        depth_chart_df=service.data.get_week_depth_chart(
            season=season,
            week=week,
        ),
        use_espn_qb_starter_signal=True,
    )
    projections_by_id = {
        projection.espn_id: projection
        for projection in pool_projections
    }

    for espn_id, player in tuple(players_by_id.items()):
        projection = projections_by_id[espn_id]
        predicted_points = projection.predicted_points
        projection_reason = projection.reason
        resolved_team = player.team or projection.team
        is_on_bye = projection.is_on_bye

        if is_on_bye:
            predicted_points = 0.0
            projection_reason = (
                f"{resolved_team} is on bye in week {week}."
            )
        elif (
            player.availability == "unavailable"
            and predicted_points is not None
        ):
            predicted_points = 0.0
            projection_reason = (
                f"ESPN lists this player as "
                f"{player.injury_status}."
            )

        players_by_id[espn_id] = player.model_copy(
            update={
                "team": resolved_team,
                "opponent_team": projection.opponent_team,
                "base_predicted_points": (
                    projection.predicted_points
                ),
                "predicted_points": predicted_points,
                "projection_status": projection.status,
                "projection_method": (
                    projection.projection_method
                ),
                "player_id": projection.player_id,
                "history_games": projection.history_games,
                "projection_reason": projection_reason,
                "is_on_bye": is_on_bye,
            }
        )

    players = sorted(
        players_by_id.values(),
        key=lambda player: (
            PLAYER_POOL_POSITION_ORDER.get(
                player.position,
                99,
            ),
            -(
                player.percent_owned
                if player.percent_owned is not None
                else -1.0
            ),
            player.player_name,
        ),
    )
    available_count = sum(
        player.roster_status == "available"
        for player in players
    )

    saved = record_predictions(
        service, season=season, week=week, scope=f"espn:{league_id}",
        generated_at=datetime.now(timezone.utc),
        strict=strict_history, schedule=history_schedule,
        samples=[{
            "player_id": projections_by_id[player.espn_id].player_id,
            "player_name": player.player_name, "position": player.position,
            "team": player.team, "opponent_team": player.opponent_team,
            "predicted_points": player.predicted_points,
            "projection_method": player.projection_method,
            "availability": player.availability,
        } for player in players if player.projection_status == "projected" and not player.is_on_bye],
    )

    players = [ESPNLeaguePlayerResponse(**item) for item in prediction_display(
        service, season, week, f"espn:{league_id}", [player.model_dump() for player in players],
        schedule=history_schedule,
    )]
    return ESPNLeaguePlayersResponse(
        league_id=league_id,
        season=season,
        week=week,
        roster_week=roster_week,
        player_count=len(players),
        available_count=available_count,
        rostered_count=len(players) - available_count,
        players=players,
    ), saved


def build_league_players_response(league, league_id: int, season: int, week: int) -> ESPNLeaguePlayersResponse:
    response, _ = project_league_players(league, league_id, season, week)
    return response


def get_espn_projection_service(
    season: int,
) -> WeeklyProjectionService:
    return projection_services.get(season)


def get_public_league(
    league_id: int,
    season: int,
):
    try:
        league = get_league(
            league_id=league_id,
            year=season,
        )
        register_league_tracking(league_id, season, "public")
        return league

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

    register_league_tracking(config.league_id, config.season, "local")
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


def team_opponents_by_week(league, team) -> dict[int, int | None]:
    schedule = getattr(team, "schedule", [])
    periods = getattr(league.settings, "matchup_periods", None)
    if not isinstance(periods, dict):
        periods = {index + 1: [index + 1] for index in range(len(schedule))}
    team_ids = {int(item.team_id) for item in league.teams}
    opponents = {}
    for period, weeks in periods.items():
        try:
            index = int(period) - 1
            if not 0 <= index < len(schedule):
                continue
            opponent = schedule[index]
            opponent_id = int(getattr(opponent, "team_id", opponent)) if opponent is not None else None
        except (ValueError, TypeError):
            continue
        if opponent_id == int(team.team_id) or opponent_id is None or opponent_id <= 0:
            opponent_id = None
        elif opponent_id not in team_ids:
            continue
        for week in weeks:
            if 1 <= int(week) <= 18:
                opponents[int(week)] = opponent_id
    return opponents


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
            opponents_by_week=team_opponents_by_week(league, team),
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
    service: WeeklyProjectionService | None = None,
) -> ESPNMatchupResponse:
    scoreboard = list(league.scoreboard(week))
    opponents_by_team: dict[int, int | None] = {}
    scoreboard_response: list[ESPNScoreboardMatchup] = []
    for entry in scoreboard:
        home_team = getattr(entry, "home_team", None)
        away_team = getattr(entry, "away_team", None)
        home_id = int(getattr(home_team, "team_id", home_team or 0))
        away_id = int(getattr(away_team, "team_id", away_team or 0))
        if home_id > 0:
            opponents_by_team[home_id] = away_id if away_id > 0 and away_id != home_id else None
        if away_id > 0:
            opponents_by_team[away_id] = home_id if home_id > 0 and home_id != away_id else None
        if home_id > 0 and away_id > 0 and home_id != away_id:
            scoreboard_response.append(
                ESPNScoreboardMatchup(
                    home_team_id=home_id,
                    home_team_name=str(
                        getattr(home_team, "team_name", f"Team {home_id}")
                    ),
                    home_score=float(getattr(entry, "home_score", 0.0)),
                    away_team_id=away_id,
                    away_team_name=str(
                        getattr(away_team, "team_name", f"Team {away_id}")
                    ),
                    away_score=float(getattr(entry, "away_score", 0.0)),
                )
            )
    matchup = next(
        (
            matchup
            for matchup in scoreboard
            if team_id
            in {
                int(getattr(matchup.home_team, "team_id", matchup.home_team or 0)),
                int(getattr(matchup.away_team, "team_id", matchup.away_team or 0)),
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

    if opponents_by_team.get(team_id) is None:
        raise HTTPException(status_code=404, detail=f"This team has no opponent in week {week}.")
    home_team_id = int(matchup.home_team.team_id)
    away_team_id = int(matchup.away_team.team_id)

    if service is None:
        service = get_espn_projection_service(season)

    home = build_team_projection_response(
        league=league, league_id=league_id, season=season,
        team_id=home_team_id, week=week, service=service,
    )
    away = build_team_projection_response(
        league=league, league_id=league_id, season=season,
        team_id=away_team_id, week=week, service=service,
    )
    return ESPNMatchupResponse(
        opponents_by_team=opponents_by_team,
        scoreboard=scoreboard_response,
        league_id=league_id,
        league_name=str(league.settings.name),
        season=season,
        week=week,
        home_score=float(matchup.home_score),
        away_score=float(matchup.away_score),
        home=home,
        away=away,
        **estimate_win_chance(home, away, service.player_df),
    )


def build_team_projection_response(
    league,
    league_id: int,
    season: int,
    team_id: int,
    week: int,
    service: WeeklyProjectionService | None = None,
) -> ESPNTeamProjectionResponse:
    team = find_league_team(
        league=league,
        team_id=team_id,
    )

    try:
        if service is None:
            service = get_espn_projection_service(season=season)
        cache_key = (
            league_id,
            season,
            week,
            f"{roster_fingerprint(league, week)}:{getattr(service, 'generation', '')}",
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

        if item.is_on_bye:
            predicted_points = 0.0
            adjustment_reason = item.reason
        elif (
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
                projection_method=item.projection_method,
                history_games=item.history_games,
                injury_context_used=item.injury_context_used,
                unavailable_teammates=(
                    item.unavailable_teammates
                ),
                is_on_bye=item.is_on_bye,
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

    record_predictions(
        service, season=season, week=week, scope=f"espn:{league_id}",
        generated_at=cached_projection.generated_at,
        samples=[player.model_dump() for player in players
                 if player.status == "projected" and not player.is_on_bye],
    )

    players = [ESPNRosterProjectionResponse(**item) for item in prediction_display(
        service, season, week, f"espn:{league_id}", [player.model_dump() for player in players],
    )]
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


@router.post("/live", response_model=ESPNLiveResponse)
def get_public_live_scores(payload: ESPNLiveRequest):
    return live_response(LiveLeagueClient(payload.league_id, payload.season),
                         payload.season, payload.week, payload.players, f"espn:{payload.league_id}")


@router.post("/local/live", response_model=ESPNLiveResponse, include_in_schema=False)
def get_local_live_scores(payload: ESPNLocalLiveRequest, request: Request):
    config = require_local_espn_access(request)
    return live_response(LiveLeagueClient(config.league_id, config.season, config.espn_s2, config.swid),
                         config.season, payload.week, payload.players,
                         f"espn:{config.league_id}", credentials=(config.espn_s2, config.swid))


@router.post(
    "/projections",
    response_model=ESPNTeamProjectionResponse,
)
def get_public_team_projections(
    payload: ESPNTeamProjectionRequest,
) -> ESPNTeamProjectionResponse:
    if payload.refresh:
        espn_connection_cache.clear()
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )
    service = projection_services.get(payload.season, refresh=True) if payload.refresh else None
    return build_team_projection_response(
        league=league,
        league_id=payload.league_id,
        season=payload.season,
        team_id=payload.team_id,
        week=payload.week,
        service=service,
    )


@router.post(
    "/players",
    response_model=ESPNLeaguePlayersResponse,
)
def get_public_league_players(
    payload: ESPNLeaguePlayersRequest,
) -> ESPNLeaguePlayersResponse:
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )
    return build_league_players_response(
        league=league,
        league_id=payload.league_id,
        season=payload.season,
        week=payload.week,
    )


@router.post(
    "/matchup",
    response_model=ESPNMatchupResponse,
)
def get_public_matchup(
    payload: ESPNTeamProjectionRequest,
) -> ESPNMatchupResponse:
    if payload.refresh:
        espn_connection_cache.clear()
    league = get_public_league(
        league_id=payload.league_id,
        season=payload.season,
    )
    service = projection_services.get(payload.season, refresh=True) if payload.refresh else None
    return build_matchup_response(
        league=league,
        league_id=payload.league_id,
        season=payload.season,
        team_id=payload.team_id,
        week=payload.week,
        service=service,
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
    "/local/players",
    response_model=ESPNLeaguePlayersResponse,
    include_in_schema=False,
)
def get_configured_private_league_players(
    payload: ESPNLocalLeaguePlayersRequest,
    request: Request,
) -> ESPNLeaguePlayersResponse:
    config, league = get_configured_private_league(
        request
    )
    return build_league_players_response(
        league=league,
        league_id=config.league_id,
        season=config.season,
        week=payload.week,
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
    if payload.refresh:
        espn_connection_cache.clear()
    config, league = get_configured_private_league(
        request
    )

    service = projection_services.get(config.season, refresh=True) if payload.refresh else None
    return build_team_projection_response(
        league=league,
        league_id=config.league_id,
        season=config.season,
        team_id=payload.team_id,
        week=payload.week,
        service=service,
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
    if payload.refresh:
        espn_connection_cache.clear()
    config, league = get_configured_private_league(request)
    service = projection_services.get(config.season, refresh=True) if payload.refresh else None
    return build_matchup_response(
        league=league,
        league_id=config.league_id,
        season=config.season,
        team_id=payload.team_id,
        week=payload.week,
        service=service,
    )
