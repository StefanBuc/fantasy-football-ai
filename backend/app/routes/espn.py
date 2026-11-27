from typing import Any, Literal
from dataclasses import asdict
from datetime import datetime, timezone
import json
from hashlib import sha256
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
    ESPNScoreboardResponse,
    ESPNRosterProjectionResponse,
    ESPNTeamSummary,
    ESPNTeamProjectionRequest,
    ESPNTeamProjectionResponse,
    ESPNLiveRequest,
    ESPNLocalLiveRequest,
    ESPNLiveResponse,
    ESPNOptimizeRequest,
    ESPNLocalOptimizeRequest,
    OptimizerPlayer,
    OptimizedLineupResponse,
)
from app.services.weekly_projection_service import (
    WeeklyProjectionService,
)
from app.services.projection_registry import projection_services
from app.services.prediction_history import record_predictions
from app.services.espn_benchmark import espn_benchmark
from app.services.accuracy_jobs import register_league_tracking
from app.services.score_presentation import prediction_display
from app.services.live_scores import live_response, LiveLeagueClient
from app.services.matchup_probability import estimate_win_chance
from app.services.lineup_optimizer import optimize_lineup
from app.schemas.trade import LocalTradeRequest, TradeRequest, TradeRosters, TradeAnalysis
from app.services.trade_analyzer import analyze_trade
from app.config.security import auth_enabled
from app.services.account_store import accounts
from app.services.result_cache import ResultCache
from espn_api.football.constant import POSITION_MAP
from app.services.espn_connection_cache import espn_connection_cache
from app.services.espn_projection_cache import (
    ESPNProjectionCache,
    ESPNLeagueWeekProjection,
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
player_pool_cache = ESPNProjectionCache(persistent=True, namespace="espn_player_pool_v1")
optimizer_settings_cache = ResultCache(ttl_seconds=900, max_entries=16, name="optimizer_settings")

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
        eligible_slots=list(getattr(player, "eligibleSlots", []) or []),
        lineup_slot=str(getattr(player, "lineupSlot", "") or "BE"),
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
    roster_players = [
        make_roster_player(
            player=player_sources_by_id[espn_id],
            normalize_team=normalize_espn_team,
            week=week,
        )
        for espn_id in sorted(players_by_id)
    ]
    # Cache only model output. Ownership, ESPN observations, availability and
    # frozen pregame scores are still assembled from the current request.
    fingerprint = sha256(json.dumps([asdict(player) for player in roster_players],
                                    sort_keys=True).encode()).hexdigest()

    def build_pool():
        roster_df, roster_week = service.data.get_projection_roster(season=season, week=week)
        projections = project_espn_roster(
            weekly_service=service, roster_players=roster_players,
            id_map=service.data.get_player_id_map(), roster_df=roster_df,
            opponents=service.data.get_week_opponents(season=season, week=week),
            season=season, week=week,
            depth_chart_df=service.data.get_week_depth_chart(season=season, week=week),
            use_espn_qb_starter_signal=True,
        )
        return ESPNLeagueWeekProjection(datetime.now(timezone.utc), roster_week, {0: tuple(projections)})

    pool, _ = player_pool_cache.get_or_create(
        (league_id, season, week, f"{fingerprint}:{getattr(service, 'generation', '')}"),
        build_pool,
    )
    projections_by_id = {
        projection.espn_id: projection
        for projection in pool.team_projections[0]
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
        generated_at=pool.generated_at,
        strict=strict_history, schedule=history_schedule,
        samples=[{
            "player_id": projections_by_id[player.espn_id].player_id,
            "player_name": player.player_name, "position": player.position,
            "team": player.team, "opponent_team": player.opponent_team,
            "predicted_points": player.predicted_points,
            "projection_method": player.projection_method,
            "availability": player.availability,
            **espn_benchmark(player_sources_by_id[player.espn_id], week),
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
        roster_week=pool.roster_week,
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
    if auth_enabled():
        if not getattr(request.state, "owner_authenticated", False):
            raise HTTPException(401, "Sign in to access a private league.")
        id = request.headers.get("X-League-Connection") or request.query_params.get("connection_id")
        try:
            return accounts.private_config(id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
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
        if auth_enabled():
            accounts.mark_expired(request.headers.get("X-League-Connection") or request.query_params.get("connection_id"))
        raise HTTPException(
            status_code=403,
            detail=(
                "The private ESPN credentials were not accepted. Update the saved connection's cookies."
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

    register_league_tracking(config.league_id, config.season, "saved" if auth_enabled() else "local")
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


def build_scoreboard_response(league, week: int) -> ESPNScoreboardResponse:
    """Fetch weekly scores without loading NFL data or running any model."""
    periods = getattr(league.settings, "matchup_periods", {})
    period = next((int(key) for key, weeks in periods.items() if week in weeks), week)
    data = league.espn_request.league_get(
        params={"view": ["mMatchupScore", "mScoreboard"], "scoringPeriodId": week},
        headers={"x-fantasy-filter": json.dumps({
            "schedule": {"filterMatchupPeriodIds": {"value": [period]}}
        })},
    )
    teams = {int(team.team_id): str(team.team_name) for team in league.teams}
    opponents: dict[int, int | None] = {}
    games = []

    def score(side):
        # ESPN's summary total can stay zero while the live total is populated.
        weekly = side.get("pointsByScoringPeriod", {}).get(str(week))
        value = weekly if weekly is not None else side.get("totalPointsLive")
        if value is None and len(periods.get(str(period), periods.get(period, [week]))) == 1:
            value = side.get("totalPoints")
        return optional_number(value)

    for entry in data.get("schedule", []):
        if int(entry.get("matchupPeriodId", 0)) != period:
            continue
        home, away = entry.get("home", {}), entry.get("away", {})
        home_id, away_id = home.get("teamId"), away.get("teamId")
        if home_id in teams:
            opponents[home_id] = away_id if away_id in teams and away_id != home_id else None
        if away_id in teams:
            opponents[away_id] = home_id if home_id in teams and away_id != home_id else None
        if home_id not in teams or away_id not in teams or home_id == away_id:
            continue
        games.append(ESPNScoreboardMatchup(
            home_team_id=home_id, home_team_name=teams[home_id], home_score=score(home),
            away_team_id=away_id, away_team_name=teams[away_id], away_score=score(away),
        ))
    return ESPNScoreboardResponse(week=week, checked_at=datetime.now(timezone.utc),
                                  opponents_by_team=opponents, scoreboard=games)


@router.post("/scoreboard", response_model=ESPNScoreboardResponse)
def get_public_scoreboard(payload: ESPNLeaguePlayersRequest):
    league = get_public_league(payload.league_id, payload.season)
    return build_scoreboard_response(league, payload.week)


@router.post("/local/scoreboard", response_model=ESPNScoreboardResponse, include_in_schema=False)
def get_local_scoreboard(payload: ESPNLocalLeaguePlayersRequest, request: Request):
    _, league = get_configured_private_league(request)
    return build_scoreboard_response(league, payload.week)


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


def cached_league_projection(league, league_id, season, week, service):
    key = (league_id, season, week,
           f"{roster_fingerprint(league, week)}:{getattr(service, 'generation', '')}")
    return projection_cache.get_or_create(key=key, builder=lambda: build_league_week_projection(
        league=league, service=service, season=season, week=week,
        normalize_team=normalize_espn_team))


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
        cached_projection, cache_hit = cached_league_projection(league, league_id, season, week, service)
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
        samples=[{**player.model_dump(), **espn_benchmark(current_players.get(player.espn_id), week)} for player in players
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


def optimizer_slot_counts(league, league_id, season):
    cookies = getattr(getattr(league, "espn_request", None), "cookies", None)
    key = (league_id, season, sha256(repr(cookies).encode()).hexdigest())
    def load():
        raw = league.espn_request.league_get(params={"view": "mSettings"})
        counts = raw.get("settings", {}).get("rosterSettings", {}).get("lineupSlotCounts", {})
        if not counts:
            raise ValueError("ESPN did not return lineup slot settings.")
        return {POSITION_MAP.get(int(slot), f"Slot {slot}"): int(count) for slot, count in counts.items()}
    return optimizer_settings_cache.get_or_create(key, load)


def build_optimized_lineup(league, league_id, season, team_id, week, include_free_agents, refresh=False):
    team = find_league_team(league, team_id)
    try:
        if refresh:
            optimizer_settings_cache.clear()
        counts = optimizer_slot_counts(league, league_id, season)
        service = projection_services.get(season, refresh=True) if refresh else get_espn_projection_service(season)
        if include_free_agents:
            pool = build_league_players_response(league, league_id, season, week)
            sources = [player for player in pool.players
                       if player.fantasy_team_id == team_id or player.roster_status == "available"]
            candidates = [OptimizerPlayer(**{
                **player.model_dump(), "current_slot": player.lineup_slot,
                "is_free_agent": player.roster_status == "available", "status": player.projection_status,
            }) for player in sources]
        else:
            projected = build_team_projection_response(league, league_id, season, team_id, week, service)
            raw_players = {int(player.playerId): player for player in team.roster}
            candidates = [OptimizerPlayer(**{
                **player.model_dump(), "current_slot": player.lineup_slot,
                "eligible_slots": list(getattr(raw_players.get(player.espn_id), "eligibleSlots", []) or []),
                "is_free_agent": False,
            }) for player in projected.players]
        result = optimize_lineup(candidates, counts)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ESPNUnknownError, ESPNAccessDenied) as error:
        raise HTTPException(status_code=502, detail="ESPN lineup settings or player availability could not be loaded.") from error
    return OptimizedLineupResponse(season=season, week=week, team_id=team_id,
        team_name=str(team.team_name), include_free_agents=include_free_agents,
        generated_at=datetime.now(timezone.utc), **result)


def build_trade_rosters(league):
    return TradeRosters(teams=[{
        "team_id": int(team.team_id), "team_name": str(team.team_name),
        "players": [{"espn_id": int(player.playerId), "player_name": str(player.name),
                     "position": str(player.position), "team": player_pro_team(player),
                     "injury_status": normalize_injury_status(getattr(player, "injuryStatus", None))}
                    for player in team.roster if str(player.position).upper() in PLAYER_POOL_POSITIONS],
    } for team in league.teams])


def trade_week_profiles(league, league_id, season, week, service):
    projection, _ = cached_league_projection(league, league_id, season, week, service)
    profiles = {}
    for team in league.teams:
        raw = {int(player.playerId): player for player in team.roster}
        players = []
        for item in projection.team_projections.get(int(team.team_id), ()):
            source = raw.get(item.espn_id)
            injury = normalize_injury_status(getattr(source, "injuryStatus", None))
            availability = classify_availability(injury)
            players.append(OptimizerPlayer(
                espn_id=item.espn_id, player_id=item.player_id, player_name=item.player_name,
                position=item.position, team=item.team, opponent_team=item.opponent_team,
                current_slot=str(getattr(source, "lineupSlot", item.lineup_slot) or "BE"),
                eligible_slots=list(getattr(source, "eligibleSlots", []) or []),
                status=item.status, projection_method=item.projection_method,
                predicted_points=0.0 if item.is_on_bye or availability == "unavailable" else item.predicted_points,
                is_on_bye=item.is_on_bye, availability=availability, injury_status=injury,
            ))
        profiles[int(team.team_id)] = [OptimizerPlayer(**item) for item in prediction_display(
            service, season, week, f"espn:{league_id}", [p.model_dump() for p in players])]
    return profiles


def build_trade_analysis(league, league_id, season, payload):
    # Validate live ownership before loading season data or running forecasts.
    for team_id, ids in ((payload.team_a_id, payload.team_a_player_ids), (payload.team_b_id, payload.team_b_player_ids)):
        team = find_league_team(league, team_id)
        if not set(ids).issubset({int(p.playerId) for p in team.roster}):
            raise HTTPException(status_code=400, detail="A selected player is no longer on the sending team. Reload rosters and select the trade again.")
    try:
        counts = optimizer_slot_counts(league, league_id, season)
        # Reject unsupported settings before expensive model work.
        optimize_lineup([], counts)
        service = get_espn_projection_service(season)
        schedule = service.data.schedule
        available_weeks = set(schedule.loc[(schedule["season"] == season) & (schedule["game_type"] == "REG"), "week"].astype(int))
        if not set(range(payload.week, payload.end_week + 1)).issubset(available_weeks):
            raise ValueError("The NFL regular-season schedule does not cover every selected week. Adjust the effective or last week.")
        return analyze_trade(season=season, request=payload,
            team_names={int(t.team_id): str(t.team_name) for t in league.teams}, slot_counts=counts,
            load_week=lambda week: trade_week_profiles(league, league_id, season, week, service))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ESPNUnknownError, ESPNAccessDenied) as error:
        raise HTTPException(status_code=502, detail="ESPN trade data could not be loaded. Try again shortly.") from error


@router.post("/trade-rosters", response_model=TradeRosters)
def get_public_trade_rosters(payload: ESPNLeagueConnectRequest):
    return build_trade_rosters(get_public_league(league_id=payload.league_id, season=payload.season))


@router.post("/local/trade-rosters", response_model=TradeRosters, include_in_schema=False)
def get_local_trade_rosters(request: Request):
    _, league = get_configured_private_league(request)
    return build_trade_rosters(league)


@router.post("/trade-analysis", response_model=TradeAnalysis)
def get_public_trade_analysis(payload: TradeRequest):
    league = get_public_league(league_id=payload.league_id, season=payload.season)
    return build_trade_analysis(league, payload.league_id, payload.season, payload)


@router.post("/local/trade-analysis", response_model=TradeAnalysis, include_in_schema=False)
def get_local_trade_analysis(payload: LocalTradeRequest, request: Request):
    config, league = get_configured_private_league(request)
    return build_trade_analysis(league, config.league_id, config.season, payload)


@router.post("/optimized-lineup", response_model=OptimizedLineupResponse)
def get_public_optimized_lineup(payload: ESPNOptimizeRequest):
    if payload.refresh:
        espn_connection_cache.clear()
    league = get_public_league(league_id=payload.league_id, season=payload.season)
    return build_optimized_lineup(league, payload.league_id, payload.season, payload.team_id,
                                 payload.week, payload.include_free_agents, payload.refresh)


@router.post("/local/optimized-lineup", response_model=OptimizedLineupResponse, include_in_schema=False)
def get_local_optimized_lineup(payload: ESPNLocalOptimizeRequest, request: Request):
    if payload.refresh:
        espn_connection_cache.clear()
    config, league = get_configured_private_league(request)
    return build_optimized_lineup(league, config.league_id, config.season, payload.team_id,
                                 payload.week, payload.include_free_agents, payload.refresh)


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
