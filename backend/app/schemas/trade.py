from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.espn import ESPNLeagueConnectRequest, OptimizedSlot


class LocalTradeRequest(BaseModel):
    team_a_id: int = Field(gt=0)
    team_b_id: int = Field(gt=0)
    team_a_player_ids: list[int] = Field(min_length=1, max_length=10)
    team_b_player_ids: list[int] = Field(min_length=1, max_length=10)
    week: int = Field(ge=1, le=18)
    end_week: int = Field(ge=1, le=18)

    @model_validator(mode="after")
    def valid_exchange(self):
        if self.team_a_id == self.team_b_id:
            raise ValueError("Choose two different teams.")
        if self.end_week < self.week:
            raise ValueError("The last week must be on or after the selected week.")
        ids = self.team_a_player_ids + self.team_b_player_ids
        if len(ids) != len(set(ids)):
            raise ValueError("Each player can appear only once in a trade.")
        return self


class TradeRequest(LocalTradeRequest, ESPNLeagueConnectRequest):
    season: int = Field(ge=2020, le=date.today().year)


class TradeRosterPlayer(BaseModel):
    espn_id: int
    player_name: str
    position: str
    team: str | None
    injury_status: str | None


class TradeRosterTeam(BaseModel):
    team_id: int
    team_name: str
    players: list[TradeRosterPlayer]


class TradeRosters(BaseModel):
    teams: list[TradeRosterTeam]


class TradePlayerValue(TradeRosterPlayer):
    from_team_id: int
    weekly_points: float | None
    rest_of_season_points: float | None
    projected_games: int
    missing_weeks: int


class TradeWeekImpact(BaseModel):
    week: int
    before_points: float | None
    after_points: float | None
    change: float | None


class TradePositionImpact(BaseModel):
    slot: str
    before_points: float | None
    after_points: float | None
    league_average: float | None
    backups_before: int
    backups_after: int


class TradeTeamImpact(BaseModel):
    team_id: int
    team_name: str
    weekly_before: float | None
    weekly_after: float | None
    weekly_change: float | None
    rest_before: float | None
    rest_after: float | None
    rest_change: float | None
    weeks_covered: int
    power_rank_before: int | None
    power_rank_after: int | None
    lineup_before: list[OptimizedSlot]
    lineup_after: list[OptimizedSlot]
    positions: list[TradePositionImpact]
    weeks: list[TradeWeekImpact]
    explanations: list[str]


class TradePowerRank(BaseModel):
    team_id: int
    team_name: str
    before_points: float | None
    after_points: float | None
    rank_before: int | None
    rank_after: int | None


class TradeAnalysis(BaseModel):
    season: int
    week: int
    end_week: int
    generated_at: datetime
    verdict: str
    favors_team_id: int | None
    summary: str
    players: list[TradePlayerValue]
    teams: list[TradeTeamImpact]
    power_rankings: list[TradePowerRank]
    notes: list[str]
