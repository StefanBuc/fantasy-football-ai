from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ESPNTeamSummary(BaseModel):
    team_id: int
    team_name: str
    abbreviation: str
    logo_url: str | None = None
    standing: int
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    streak: str | None = None
    playoff_pct: float | None = None


class ESPNLeagueConnectResponse(BaseModel):
    league_id: int
    season: int
    current_week: int
    league_name: str
    team_count: int
    teams: list[ESPNTeamSummary]


class ESPNLeagueConnectRequest(BaseModel):
    league_id: int = Field(gt=0)
    season: int = Field(
        ge=2018,
        le=date.today().year,
    )


class ESPNTeamProjectionRequest(BaseModel):
    refresh: bool = False
    league_id: int = Field(gt=0)
    season: int = Field(
        ge=2020,
        le=date.today().year,
    )
    team_id: int = Field(gt=0)
    week: int = Field(ge=1, le=18)


class ESPNLocalTeamProjectionRequest(BaseModel):
    refresh: bool = False
    team_id: int = Field(gt=0)
    week: int = Field(ge=1, le=18)


class ESPNLeaguePlayersRequest(BaseModel):
    league_id: int = Field(gt=0)
    season: int = Field(
        ge=2018,
        le=date.today().year,
    )
    week: int = Field(ge=1, le=18)


class ESPNLocalLeaguePlayersRequest(BaseModel):
    week: int = Field(ge=1, le=18)


class ESPNLeaguePlayerResponse(BaseModel):
    espn_id: int
    player_name: str
    position: str
    team: str | None
    roster_status: Literal["available", "rostered"]
    fantasy_team_id: int | None
    fantasy_team_name: str | None
    percent_owned: float | None
    percent_started: float | None
    season_average: float | None
    opponent_team: str | None
    base_predicted_points: float | None
    predicted_points: float | None
    projection_status: Literal["projected", "skipped"]
    projection_method: Literal[
        "model",
        "recent_average",
        "position_average",
    ] | None
    history_games: int | None
    projection_reason: str | None
    is_on_bye: bool
    injury_status: str | None
    availability: Literal[
        "healthy",
        "questionable",
        "doubtful",
        "unavailable",
        "unknown",
    ]


class ESPNLeaguePlayersResponse(BaseModel):
    league_id: int
    season: int
    week: int
    roster_week: int
    player_count: int
    available_count: int
    rostered_count: int
    players: list[ESPNLeaguePlayerResponse]


class ESPNRosterProjectionResponse(BaseModel):
    espn_id: int
    player_id: str | None
    player_name: str
    position: str
    lineup_slot: str
    team: str | None
    opponent_team: str | None
    base_predicted_points: float | None
    predicted_points: float | None
    status: Literal["projected", "skipped"]
    projection_method: Literal[
        "model",
        "recent_average",
        "position_average",
    ] | None
    history_games: int | None
    injury_context_used: bool
    unavailable_teammates: int
    is_on_bye: bool
    injury_status: str | None
    availability: Literal[
        "healthy",
        "questionable",
        "doubtful",
        "unavailable",
        "unknown",
    ]
    adjustment_reason: str | None
    reason: str | None


class ESPNTeamProjectionResponse(BaseModel):
    league_id: int
    league_name: str
    season: int
    week: int
    roster_week: int
    team_id: int
    team_name: str
    generated_at: datetime
    cache_hit: bool
    projected_count: int
    skipped_count: int
    players: list[ESPNRosterProjectionResponse]


class ESPNMatchupResponse(BaseModel):
    league_id: int
    league_name: str
    season: int
    week: int
    home_score: float
    away_score: float
    home: ESPNTeamProjectionResponse
    away: ESPNTeamProjectionResponse
