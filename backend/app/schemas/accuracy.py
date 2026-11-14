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


class AutomationJob(BaseModel):
    week: int | None
    state: Literal["running", "success", "error"]
    last_started_at: str | None
    last_finished_at: str | None
    last_success_at: str | None
    last_error: str | None
    next_run_at: str | None
    result: dict[str, int] | None


class AutomationStatus(BaseModel):
    enabled: bool
    registered: bool
    capture_enabled: bool
    note: str
    last_checked_at: str | None
    worker_error: str | None
    capture: AutomationJob | None
    sync: AutomationJob | None
    poll_seconds: int
    capture_interval_minutes: int
    capture_window_hours: int
    sync_interval_hours: int
