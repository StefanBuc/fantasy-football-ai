"""Enrich projections without changing the cached model results."""

from datetime import datetime
import sqlite3

from app.services.prediction_history import prediction_history, game_times, normalize_team, utc_now
from app.services.projection_ranges import estimate_range
from app.services.performance import logger


def prediction_display(service, season, week, scope, players, schedule=None):
    if not players:
        return []
    schedule = schedule if schedule is not None else getattr(getattr(service, "data", None), "schedule", None)
    games = game_times(schedule, season, week)
    try:
        saved = prediction_history.week_records(season, week, scope)
    except (OSError, sqlite3.Error):
        logger.warning("Saved pregame predictions unavailable for display")
        saved = {}
    results = []
    for player in players:
        item = dict(player)
        position = item["position"].replace("D/ST", "DST")
        player_id = item.get("player_id")
        key = normalize_team(player_id) if position == "DST" else str(player_id)
        frozen = saved.get((position, key))
        game = games.get(normalize_team(item.get("team")))
        kickoff = frozen["kickoff"] if frozen else game[1].isoformat() if game else None
        item.update(estimate_range(item.get("predicted_points"), position,
                                  item.get("projection_method"), getattr(service, "model_hashes", {})))
        if item.get("is_on_bye") or item.get("availability") == "unavailable":
            item.update(floor_points=None, ceiling_points=None,
                        range_note="Range unavailable for a bye or confirmed unavailable player.")
        if frozen and kickoff and datetime.fromisoformat(kickoff) <= utc_now():
            item.update({name: frozen.get(name) for name in ("floor_points", "ceiling_points", "range_note", "range_revision")})
        item.update(kickoff_at=kickoff, prediction_saved=frozen is not None,
                    pregame_predicted_points=frozen["predicted_points"] if frozen else None)
        results.append(item)
    return results
