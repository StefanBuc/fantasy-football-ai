from fastapi import (APIRouter, HTTPException, Path, Query)
from datetime import date
from typing import Annotated
from app.services.projection_registry import projection_services

from app.schemas.predictions import (
    PlayerProjectionResponse,
    Position,
    SkippedPlayerResponse,
    WeeklyProjectionResponse,
)

from app.services.weekly_projection_service import (
    WeeklyProjectionService,
)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])

def get_projection_service(season: int,) -> WeeklyProjectionService:
    return projection_services.get(season)

@router.get("/week/{season}/{week}", response_model=WeeklyProjectionResponse)
def get_weekly_projections(
    season: Annotated[
        int,
        Path(ge=2020, le=date.today().year, description="Season year"),
    ],
    week: Annotated[
        int,
        Path(ge=1, le=18, description="Week number"),
    ],
    position: Position = Query(default="QB", description="Position to project"),
    include_skipped: bool = Query(default=False, description="Whether to include skipped players in the response"),
    refresh: bool = Query(default=False, description="Reload NFL data and regenerate projections"),
) -> WeeklyProjectionResponse:
    try:
        service = (
            projection_services.get(season, refresh=True)
            if refresh else get_projection_service(season=season)
        )
        result = service.project_week(week=week, position=position)
    
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    
    projections = [
        PlayerProjectionResponse(
            player_id=item.request.player_id,
            player_name=item.request.player_name,
            position=position,
            team=item.request.team,
            opponent_team=(
                item.request.opponent_team
            ),
            season=item.request.season,
            week=item.request.upcoming_week,
            depth_position=(
                item.request.depth_position
            ),
            depth_team=item.request.depth_team,
            active_depth_rank=(
                item.request.active_depth_rank
            ),
            predicted_points=(
                item.predicted_points
            ),
            projection_method=(
                item.projection_method
            ),
            history_games=item.history_games,
            injury_context_used=item.injury_context_used,
            unavailable_teammates=(
                item.unavailable_teammates
            ),
        )
        for item in result.projections
    ]

    skipped = []

    if include_skipped:
        skipped = [
            SkippedPlayerResponse(
                player_id=item.request.player_id,
                player_name=(
                    item.request.player_name
                ),
                position=position,
                team=item.request.team,
                opponent_team=(
                    item.request.opponent_team
                ),
                season=item.request.season,
                week=(
                    item.request.upcoming_week
                ),
                depth_position=(
                    item.request.depth_position
                ),
                depth_team=(
                    item.request.depth_team
                ),
                active_depth_rank=(
                    item.request.active_depth_rank
                ),
                available_games=(
                    item.available_games
                ),
                required_games=(
                    item.required_games
                ),
                reason=item.reason,
            )
            for item in result.skipped
        ]

    return WeeklyProjectionResponse(
        generated_at=result.generated_at,
        season=season,
        week=week,
        position=position,
        projected_count=len(
            result.projections
        ),
        skipped_count=len(result.skipped),
        projections=projections,
        skipped=skipped,
    )
