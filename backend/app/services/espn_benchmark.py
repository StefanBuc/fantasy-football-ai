"""Convert ESPN's week-specific projected offensive stats to NFL full-PPR scoring."""

import math

ESPN_SCORING = "nfl_full_ppr_v1"
WEIGHTS = {
    "passingYards": 0.04, "passingTouchdowns": 4, "passingInterceptions": -2,
    "rushingYards": 0.1, "rushingTouchdowns": 6,
    "receivingYards": 0.1, "receivingTouchdowns": 6, "receivingReceptions": 1,
    "passing2PtConversions": 2, "rushing2PtConversions": 2, "receiving2PtConversions": 2,
    "lostFumbles": -2, "kickoffReturnTouchdowns": 6, "puntReturnTouchdowns": 6,
}


def espn_benchmark(player, week):
    # Never use appliedTotal/projected_points: those depend on league scoring.
    # Never substitute the current week, a season average, or actual stats.
    if getattr(player, "position", "").upper() not in {"QB", "RB", "WR", "TE"}:
        return {}
    weeks = getattr(player, "stats", None)
    if not isinstance(weeks, dict):
        return {}
    entry = weeks.get(week, weeks.get(str(week), {}))
    stats = entry.get("projected_breakdown") if isinstance(entry, dict) else None
    if not isinstance(stats, dict) or not any(key in stats for key in (
        "passingYards", "rushingYards", "receivingYards", "receivingReceptions",
    )):
        return {}
    try:
        values = {key: float(stats[key]) for key in WEIGHTS if key in stats}
    except (TypeError, ValueError, OverflowError):
        return {}
    if not all(math.isfinite(value) for value in values.values()):
        return {}
    points = sum(WEIGHTS[key] * value for key, value in values.items())
    return {"espn_predicted_points": points, "espn_scoring": ESPN_SCORING} if math.isfinite(points) else {}
