"""Small anonymous summaries of NFL-wide tracking; never league or account data."""

from contextlib import closing
from datetime import date
import sqlite3

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.prediction_history import prediction_history, SCORING, utc_now
from app.services.accuracy_jobs import nfl_season
from app.services.result_cache import ResultCache

router = APIRouter(prefix="/api/public", tags=["public"])
summary_cache = ResultCache(ttl_seconds=60, max_entries=8, name="public_performance")


class PublicPerformance(BaseModel):
    season: int
    state: str
    scoring: str = SCORING
    saved: int = 0
    compared: int = 0
    pending: int = 0
    mae: float | None = None
    within_five_pct: float | None = None
    model_compared: int = 0
    fallback_compared: int = 0
    last_result_update: str | None = None
    latest_week: int | None = None
    latest_week_mae: float | None = None
    latest_week_compared: int = 0


def read_public_performance(season):
    path = prediction_history.path
    if not path.exists():
        return PublicPerformance(season=season, state="collecting")
    # The public endpoint cannot create, migrate, or write to the history DB.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("""SELECT COUNT(*) AS saved, COUNT(actual_points) AS compared,
            AVG(ABS(predicted_points-actual_points)) AS mae,
            AVG(CASE WHEN actual_points IS NOT NULL THEN
                CASE WHEN ABS(predicted_points-actual_points)<=5 THEN 100.0 ELSE 0.0 END END) AS within_five_pct,
            SUM(CASE WHEN actual_points IS NOT NULL AND projection_method='model' THEN 1 ELSE 0 END) AS model_compared,
            MAX(CASE WHEN actual_points IS NOT NULL THEN actual_updated_at END) AS last_result_update,
            MAX(CASE WHEN actual_points IS NOT NULL THEN week END) AS latest_week
            FROM predictions WHERE scope='weekly' AND season=?""", (season,)).fetchone()
        latest = db.execute("""SELECT COUNT(actual_points) AS compared,
            AVG(ABS(predicted_points-actual_points)) AS mae
            FROM predictions WHERE scope='weekly' AND season=? AND week=?""", (season, row["latest_week"])).fetchone()
        return PublicPerformance(season=season, state="ready" if row["compared"] else "collecting",
            saved=row["saved"], compared=row["compared"], pending=row["saved"]-row["compared"],
            mae=row["mae"], within_five_pct=row["within_five_pct"], model_compared=row["model_compared"] or 0,
            fallback_compared=row["compared"]-(row["model_compared"] or 0), last_result_update=row["last_result_update"],
            latest_week=row["latest_week"], latest_week_mae=latest["mae"], latest_week_compared=latest["compared"])


@router.get("/performance", response_model=PublicPerformance)
def public_performance(season: int | None = Query(default=None, ge=2020, le=date.today().year)):
    target = season if season is not None else nfl_season(utc_now())
    try:
        return summary_cache.get_or_create((str(prediction_history.path), target), lambda: read_public_performance(target))
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(503, "Public model results are temporarily unavailable.") from error
