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
    opponents_by_week: dict[int, int | None] = Field(default_factory=dict)


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


class ProjectionDisplay(BaseModel):
    floor_points: float | None = None
    ceiling_points: float | None = None
    range_note: str | None = None
    range_revision: str | None = None
    kickoff_at: datetime | None = None
    prediction_saved: bool = False
    pregame_predicted_points: float | None = None


class ESPNLeaguePlayerResponse(ProjectionDisplay):
    player_id: str | None = None
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


class ESPNRosterProjectionResponse(ProjectionDisplay):
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


class ESPNScoreboardMatchup(BaseModel):
    home_team_id: int
    home_team_name: str
    home_score: float
    away_team_id: int
    away_team_name: str
    away_score: float


class ESPNMatchupResponse(BaseModel):
    opponents_by_team: dict[int, int | None] = Field(default_factory=dict)
    scoreboard: list[ESPNScoreboardMatchup] = Field(default_factory=list)
    home_win_pct: float | None = Field(default=None, ge=0, le=100)
    away_win_pct: float | None = Field(default=None, ge=0, le=100)
    win_probability_note: str = "Pregame estimate unavailable."
    league_id: int
    league_name: str
    season: int
    week: int
    home_score: float
    away_score: float
    home: ESPNTeamProjectionResponse
    away: ESPNTeamProjectionResponse


class LivePlayerRequest(BaseModel):
    espn_id: int = Field(ge=-2147483648, le=2147483647)
    player_id: str | None = Field(default=None, max_length=64)
    position: str = Field(max_length=8)
    team: str | None = Field(default=None, max_length=8)


class ESPNLiveRequest(ESPNLeagueConnectRequest):
    week: int = Field(ge=1, le=18)
    players: list[LivePlayerRequest] = Field(max_length=1200)


class ESPNLocalLiveRequest(BaseModel):
    week: int = Field(ge=1, le=18)
    players: list[LivePlayerRequest] = Field(max_length=1200)


class LivePlayerScore(ProjectionDisplay):
    espn_id: int
    game_state: Literal["pregame", "live", "final", "postponed", "bye", "unknown"]
    live_points: float | None
    game_detail: str | None = None


class ESPNLiveResponse(BaseModel):
    season: int
    week: int
    checked_at: datetime
    note: str
    players: list[LivePlayerScore]
