from typing import Literal

from pydantic import BaseModel

AccuracyPosition = Literal["QB", "RB", "WR", "TE", "K", "DST"]


class AccuracyMetrics(BaseModel):
    saved: int
    scored: int
    pending: int
    mae: float | None
    bias: float | None


class PositionMetrics(AccuracyMetrics):
    position: AccuracyPosition


class WeekMetrics(AccuracyMetrics):
    week: int


class ModelMetrics(AccuracyMetrics):
    model_version: str
    model_revision: str
    projection_method: str


class PredictionRecord(BaseModel):
    season: int
    week: int
    player_id: str
    player_name: str | None
    position: AccuracyPosition
    team: str
    opponent_team: str
    predicted_points: float
    actual_points: float | None
    error: float | None
    projection_method: str
    model_version: str
    model_revision: str
    generated_at: str
    recorded_at: str
    kickoff: str
    actual_updated_at: str | None


class AccuracyReport(BaseModel):
    season: int
    scoring: str
    summary: AccuracyMetrics
    by_position: list[PositionMetrics]
    by_model: list[ModelMetrics]
    weekly_trend: list[WeekMetrics]
    records: list[PredictionRecord]
    limit: int
    offset: int


class SyncResult(BaseModel):
    updated_count: int
    checked_count: int
