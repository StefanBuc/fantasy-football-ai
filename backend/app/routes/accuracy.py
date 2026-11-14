from datetime import date
import sqlite3
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from filelock import Timeout

from app.schemas.accuracy import AccuracyPosition, AccuracyReport, SyncResult, AutomationStatus
from app.services.prediction_history import prediction_history
from app.services.prediction_actuals import sync_actuals
from app.services.performance import logger
from app.services.accuracy_jobs import accuracy_jobs, operation_lock, run_tracked_sync

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])
Season = Annotated[int, Path(ge=2020, le=date.today().year)]
League = Annotated[int | None, Query(ge=1)]
sync_lock = Lock()


def history_scope(league_id):
    return f"espn:{league_id}" if league_id is not None else "weekly"


@router.get("/{season}", response_model=AccuracyReport)
def get_accuracy(season: Season, league_id: League = None,
                 week: Annotated[int | None, Query(ge=1, le=18)] = None,
                 position: AccuracyPosition | None = None,
                 limit: Annotated[int, Query(ge=1, le=200)] = 100,
                 offset: Annotated[int, Query(ge=0)] = 0):
    try:
        return prediction_history.report(season, history_scope(league_id), week, position, limit, offset)
    except (OSError, sqlite3.Error) as error:
        logger.warning("Prediction history unavailable: %s", error)
        raise HTTPException(503, "Prediction history could not be opened. Check the backend data directory.") from error


@router.post("/{season}/sync", response_model=SyncResult)
def sync_results(season: Season, league_id: League = None):
    if not sync_lock.acquire(blocking=False):
        raise HTTPException(409, "A results sync is already running. Try again when it finishes.")
    try:
        with operation_lock():
            scope = history_scope(league_id)
            return run_tracked_sync(season, scope, lambda: sync_actuals(prediction_history, season, scope))
    except Timeout as error:
        raise HTTPException(409, "An automatic capture or results sync is running. Try again when it finishes.") from error
    except Exception as error:
        logger.warning("Prediction results sync failed: %s", error)
        raise HTTPException(503, "Results could not be synced. Saved predictions are preserved; try again later.") from error
    finally:
        sync_lock.release()


@router.get("/{season}/automation", response_model=AutomationStatus)
def get_automation_status(season: Season, league_id: League = None):
    try:
        return accuracy_jobs.status(season, history_scope(league_id))
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, "Automatic tracking status could not be read.") from error
