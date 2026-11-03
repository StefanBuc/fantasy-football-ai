from dataclasses import asdict
from datetime import datetime
import json

from app.services.projection_types import (
    PlayerProjection, PlayerProjectionRequest, ProjectionSlateResult, SkippedPlayerProjection,
)


def encode_slate(result: ProjectionSlateResult) -> bytes:
    return json.dumps(asdict(result), default=lambda value: value.isoformat(),
                      allow_nan=False).encode()


def decode_slate(payload: bytes) -> ProjectionSlateResult:
    data = json.loads(payload)
    def items(name, cls):
        return [cls(**{**item, "request": PlayerProjectionRequest(**item["request"])})
                for item in data[name]]
    return ProjectionSlateResult(
        projections=items("projections", PlayerProjection),
        skipped=items("skipped", SkippedPlayerProjection),
        generated_at=datetime.fromisoformat(data["generated_at"]),
    )
