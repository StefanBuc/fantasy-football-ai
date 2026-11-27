import json
from fastapi import APIRouter, HTTPException
from app.services.retraining_worker import training_status

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/status")
def status():
    try:
        return training_status()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(503, "Retraining status could not be read. Current model files are preserved.") from error
