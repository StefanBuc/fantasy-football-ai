from typing import Literal

from pydantic import BaseModel

Position = Literal["QB", "RB", "WR", "TE"]


class ProjectionPlayerBase(BaseModel):
    player_id: str
    player_name: str | None
    position: Position
    team: str | None
    opponent_team: str
    season: int
    week: int
    depth_position: str | None
    depth_team: int | None
    active_depth_rank: int | None


class PlayerProjectionResponse(
    ProjectionPlayerBase
):
    predicted_points: float
    projection_method: Literal[
        "model",
        "recent_average",
        "position_average",
    ]
    history_games: int | None
    injury_context_used: bool
    unavailable_teammates: int


class SkippedPlayerResponse(
    ProjectionPlayerBase
):
    available_games: int
    required_games: int
    reason: str


class WeeklyProjectionResponse(BaseModel):
    season: int
    week: int
    position: Position
    projected_count: int
    skipped_count: int
    projections: list[
        PlayerProjectionResponse
    ]
    skipped: list[
        SkippedPlayerResponse
    ]
