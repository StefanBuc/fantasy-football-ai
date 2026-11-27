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
    floor_points: float | None = None
    ceiling_points: float | None = None
    range_result: Literal["pending", "unavailable", "below", "inside", "above"]
    espn_predicted_points: float | None = None
    espn_scoring: str | None = None
    espn_recorded_at: str | None = None
    espn_error: float | None = None


class RangeMetrics(BaseModel):
    count: int
    missing: int
    inside: int
    below: int
    above: int
    coverage_pct: float | None
    average_width: float | None


class PositionRangeMetrics(RangeMetrics):
    position: AccuracyPosition


class RangeCoverage(RangeMetrics):
    by_position: list[PositionRangeMetrics]


class ErrorBucket(BaseModel):
    label: str
    count: int
    pct: float | None


class ErrorDistribution(BaseModel):
    count: int
    median_absolute_error: float | None
    p90_absolute_error: float | None
    rmse: float | None
    within_two_pct: float | None
    within_five_pct: float | None
    within_ten_pct: float | None
    buckets: list[ErrorBucket]


class ESPNMetrics(BaseModel):
    count: int
    pending: int
    ai_mae: float | None
    espn_mae: float | None
    ai_closer: int
    espn_closer: int
    ties: int
    mae_improvement: float | None


class PositionESPNMetrics(ESPNMetrics):
    position: AccuracyPosition


class ESPNComparison(ESPNMetrics):
    scoring: str
    by_position: list[PositionESPNMetrics]


class AccuracyReport(BaseModel):
    season: int
    scoring: str
    summary: AccuracyMetrics
    range_coverage: RangeCoverage
    error_distribution: ErrorDistribution
    espn_comparison: ESPNComparison
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
