"""Accuracy calculations over complete filtered cohorts, before pagination."""

from datetime import datetime
import math
from statistics import median

from app.services.espn_benchmark import ESPN_SCORING


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def range_result(row):
    actual, low, high = (row.get(key) for key in ("actual_points", "floor_points", "ceiling_points"))
    if not finite(actual):
        return "pending"
    if not finite(low) or not finite(high) or low > high:
        return "unavailable"
    return "below" if actual < low else "above" if actual > high else "inside"


def range_metrics(rows):
    graded = [row for row in rows if finite(row.get("actual_points"))]
    counts = {key: 0 for key in ("inside", "below", "above", "unavailable")}
    widths = []
    for row in graded:
        result = range_result(row)
        counts[result] += 1
        if result != "unavailable":
            widths.append(row["ceiling_points"] - row["floor_points"])
    count = len(widths)
    return {"count": count, "missing": counts["unavailable"], "inside": counts["inside"],
            "below": counts["below"], "above": counts["above"],
            "coverage_pct": 100 * counts["inside"] / count if count else None,
            "average_width": sum(widths) / count if count else None}


def paired(row):
    if (row.get("position") not in {"QB", "RB", "WR", "TE"}
            or row.get("espn_scoring") != ESPN_SCORING or not finite(row.get("espn_predicted_points"))):
        return False
    try:
        observed = datetime.fromisoformat(row["espn_recorded_at"])
        kickoff = datetime.fromisoformat(row["kickoff"])
        return observed.tzinfo is not None and kickoff.tzinfo is not None and observed < kickoff
    except (KeyError, TypeError, ValueError):
        return False


def espn_metrics(rows):
    matched = [row for row in rows if paired(row) and finite(row.get("actual_points"))]
    ai = [abs(row["predicted_points"] - row["actual_points"]) for row in matched]
    espn = [abs(row["espn_predicted_points"] - row["actual_points"]) for row in matched]
    ties = sum(math.isclose(a, b, abs_tol=1e-8, rel_tol=0) for a, b in zip(ai, espn))
    ai_closer = sum(a < b and not math.isclose(a, b, abs_tol=1e-8, rel_tol=0) for a, b in zip(ai, espn))
    count = len(matched)
    ai_mae, espn_mae = (sum(values) / count if count else None for values in (ai, espn))
    return {"count": count, "pending": sum(paired(row) and row.get("actual_points") is None for row in rows),
            "ai_mae": ai_mae, "espn_mae": espn_mae, "ai_closer": ai_closer,
            "espn_closer": count - ties - ai_closer, "ties": ties,
            "mae_improvement": espn_mae - ai_mae if count else None}


def insights(rows):
    errors = [row["predicted_points"] - row["actual_points"] for row in rows if finite(row.get("actual_points"))]
    absolute = sorted(abs(value) for value in errors)
    count = len(errors)
    # Symmetric, non-overlapping intervals; exactly +/-2 belongs in the middle.
    buckets = [0] * 7
    for error in errors:
        size = abs(error)
        if size <= 2:
            index = 3
        elif size <= 5:
            index = 2 if error < 0 else 4
        elif size <= 10:
            index = 1 if error < 0 else 5
        else:
            index = 0 if error < 0 else 6
        buckets[index] += 1
    p90 = None
    if count:
        at = (count - 1) * 0.9
        left, right = math.floor(at), math.ceil(at)
        p90 = absolute[left] + (absolute[right] - absolute[left]) * (at - left)
    return {
        "range_coverage": {**range_metrics(rows), "by_position": [
            {"position": position, **range_metrics([row for row in rows if row["position"] == position])}
            for position in ("QB", "RB", "WR", "TE", "K", "DST")]},
        "error_distribution": {"count": count, "median_absolute_error": median(absolute) if count else None,
            "p90_absolute_error": p90, "rmse": math.sqrt(sum(value * value for value in errors) / count) if count else None,
            "within_two_pct": 100 * sum(value <= 2 for value in absolute) / count if count else None,
            "within_five_pct": 100 * sum(value <= 5 for value in absolute) / count if count else None,
            "within_ten_pct": 100 * sum(value <= 10 for value in absolute) / count if count else None,
            "buckets": [{"label": label, "count": total, "pct": 100 * total / count if count else None}
                for label, total in zip(("Under by >10", "Under by >5–10", "Under by >2–5", "Within 2", "Over by >2–5", "Over by >5–10", "Over by >10"), buckets)]},
        "espn_comparison": {**espn_metrics(rows), "scoring": "Full-PPR offense; ESPN projected stats converted to the app's scoring.",
            "by_position": [{"position": position, **espn_metrics([row for row in rows if row["position"] == position])}
                for position in ("QB", "RB", "WR", "TE")]},
    }
