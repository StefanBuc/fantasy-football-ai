from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerProjectionRequest:
    player_id: str
    season: int
    upcoming_week: int
    opponent_team: str
    player_name: str | None = None
    team: str | None = None
    
@dataclass(frozen=True)
class PlayerProjection:
    request: PlayerProjectionRequest
    position: str
    predicted_points: float


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