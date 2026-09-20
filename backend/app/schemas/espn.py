from datetime import date

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
    league_id: int
    season: int