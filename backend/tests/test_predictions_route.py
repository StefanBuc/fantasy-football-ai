from fastapi.testclient import TestClient

from main import app
from app.routes import predictions as predictions_route
from app.services.projection_types import (
    PlayerProjection,
    PlayerProjectionRequest,
    ProjectionSlateResult,
)


class FakeProjectionService:
    def project_week(
        self,
        week: int,
        position: str,
    ) -> ProjectionSlateResult:
        request = PlayerProjectionRequest(
            player_id="qb-1",
            player_name="Test Quarterback",
            team="BUF",
            season=2024,
            upcoming_week=week,
            opponent_team="ARI",
            depth_position="QB",
            depth_team=1,
            active_depth_rank=1,
        )

        projection = PlayerProjection(
            request=request,
            position=position,
            predicted_points=20.5,
        )

        return ProjectionSlateResult(
            projections=[projection],
            skipped=[],
        )


def test_weekly_projection_endpoint_returns_contract(
    monkeypatch,
):
    monkeypatch.setattr(
        predictions_route,
        "get_projection_service",
        lambda season: FakeProjectionService(),
    )

    client = TestClient(app)

    response = client.get(
        "/api/predictions/week/2024/1",
        params={"position": "QB"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["season"] == 2024
    assert body["week"] == 1
    assert body["position"] == "QB"
    assert body["projected_count"] == 1
    assert body["skipped_count"] == 0
    assert body["projections"][0]["player_id"] == "qb-1"
    assert body["projections"][0]["predicted_points"] == 20.5