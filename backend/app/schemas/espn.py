from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ESPNTeamSummary(BaseModel):
    team_id: int
    team_name: str
    abbreviation: str
    logo_url: str | None = None


class ESPNLeagueConnectResponse(BaseModel):
    league_id: int
    season: int
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
    league_id: int = Field(gt=0)
    season: int = Field(
        ge=2020,
        le=date.today().year,
    )
    team_id: int = Field(gt=0)
    week: int = Field(ge=1, le=18)


class ESPNRosterProjectionResponse(BaseModel):
    espn_id: int
    player_id: str | None
    player_name: str
    position: str
    lineup_slot: str
    team: str | None
    opponent_team: str | None
    predicted_points: float | None
    status: Literal["projected", "skipped"]
    reason: str | None


class ESPNTeamProjectionResponse(BaseModel):
    league_id: int
    league_name: str
    season: int
    week: int
    team_id: int
    team_name: str
    projected_count: int
    skipped_count: int
    players: list[ESPNRosterProjectionResponse]
