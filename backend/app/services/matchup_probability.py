"""Pregame approximation; these probabilities have not been calibrated on outcomes."""

from math import isfinite, sqrt
from statistics import NormalDist

import pandas as pd


# Conservative standard deviations for players without enough usable history.
# These are explicit heuristic defaults, not fitted uncertainty estimates.
FALLBACK_STD = {"QB": 8.0, "RB": 9.0, "WR": 9.0, "TE": 7.0, "K": 5.0, "DST": 7.0}
METHOD_NOTE = (
    "Pregame estimate from projected starters and historical scoring variability. "
    "Uses a normal approximation with independent player scores and heuristic "
    "defaults for limited history. Not yet validated against actual matchup outcomes; "
    "excludes live ESPN scores."
)


def _variance(player, history: pd.DataFrame, season: int, week: int) -> float:
    fallback = FALLBACK_STD.get(player.position, 9.0) ** 2
    required = {"player_id", "season", "week", "fantasy_points_ppr"}
    if not player.player_id or not required.issubset(history.columns):
        return fallback
    prior = history[
        (history["player_id"].astype(str) == str(player.player_id))
        & ((history["season"] < season)
           | ((history["season"] == season) & (history["week"] < week)))
    ].sort_values(["season", "week"]).tail(16)
    points = pd.to_numeric(prior["fantasy_points_ppr"], errors="coerce").dropna()
    points = points[points.map(lambda value: isfinite(value))]
    if len(points) < 4:
        return fallback
    # Shrink short histories toward the position default, avoiding false precision.
    return max(4.0, (len(points) * float(points.var()) + 4 * fallback) / (len(points) + 4))


def estimate_win_chance(home, away, history: pd.DataFrame) -> dict:
    totals = []
    variances = []
    for team in (home, away):
        starters = [player for player in team.players if player.lineup_slot not in {"BE", "IR"}]
        if not starters:
            return {"home_win_pct": None, "away_win_pct": None,
                    "win_probability_note": "Win chance unavailable: no starting lineup was found."}
        total = variance = 0.0
        for player in starters:
            if player.is_on_bye or player.availability == "unavailable":
                continue
            if player.status != "projected" or player.predicted_points is None or not isfinite(player.predicted_points):
                return {"home_win_pct": None, "away_win_pct": None,
                        "win_probability_note": "Win chance unavailable: some starters have no projection."}
            total += player.predicted_points
            variance += _variance(player, history, team.season, team.week)
        totals.append(total)
        variances.append(variance)
    difference = totals[0] - totals[1]
    variance = sum(variances)
    if variance > 0:
        probability = NormalDist().cdf(difference / sqrt(variance))
    else:
        probability = 0.5 if difference == 0 else float(difference > 0)
    home_pct = round(probability * 100, 1)
    return {"home_win_pct": home_pct, "away_win_pct": round(100 - home_pct, 1),
            "win_probability_note": METHOD_NOTE}
