from dataclasses import dataclass
from typing import Literal


ProjectionMethod = Literal[
    "model",
    "recent_average",
    "position_average",
]


@dataclass(frozen=True)
class PlayerProjectionRequest:
    player_id: str
    season: int
    upcoming_week: int
    opponent_team: str
    player_name: str | None = None
    team: str | None = None
    depth_position: str | None = None
    depth_team: int | None = None
    active_depth_rank: int | None = None
    teammate_out_count: float = 0.0
    teammate_out_target_share: float = 0.0
    teammate_out_carries: float = 0.0
    teammate_out_offense_pct: float = 0.0
    
@dataclass(frozen=True)
class PlayerProjection:
    request: PlayerProjectionRequest
    position: str
    predicted_points: float
    projection_method: ProjectionMethod = "model"
    history_games: int | None = None
    injury_context_used: bool = False
    unavailable_teammates: int = 0


@dataclass(frozen=True)
class SkippedPlayerProjection:
    request: PlayerProjectionRequest
    available_games: int
    required_games: int
    reason: str


@dataclass(frozen=True)
class ProjectionSlateResult:
    projections: list[PlayerProjection]
    skipped: list[SkippedPlayerProjection]
