"""Reconcile saved forecasts with published stats, without loading inference data."""

from datetime import datetime, timedelta
import math

import nfl_data_py as nfl
import pandas as pd

from app.services.NFL_data import NFLData
from app.services.prediction_history import game_times, normalize_team, utc_now
from app.services.special_teams_data import load_special_teams_weekly


def next_morning(kickoff):
    kickoff = pd.Timestamp(kickoff)
    eastern_date = kickoff.tz_convert("America/New_York").date() + timedelta(days=1)
    morning = pd.Timestamp(f"{eastern_date} 08:00").tz_localize("America/New_York").tz_convert("UTC")
    return max(kickoff + timedelta(hours=12), morning).to_pydatetime()


def reconcile(history, season, scope, schedule, weekly, special, now=None, automatic=False):
    now = now or utc_now()
    rows = history.rows(season, scope)
    games_by_week = {week: game_times(schedule, season, week) for week in {row["week"] for row in rows}}
    actuals = {}
    duplicates = set()

    def add(key, points):
        try:
            points = float(points)
        except (TypeError, ValueError):
            return
        if not math.isfinite(points):
            return
        if key in actuals:
            duplicates.add(key)
        actuals[key] = points

    if weekly is not None and not weekly.empty:
        regular = weekly[weekly.season_type == "REG"] if "season_type" in weekly else weekly
        for item in regular.to_dict("records"):
            if item.get("position") not in {"QB", "RB", "WR", "TE"}:
                continue
            add((item["position"], int(item["season"]), int(item["week"]), str(item["player_id"]),
                 normalize_team(item.get("recent_team", item.get("team")))), item.get("fantasy_points_ppr"))
    for position, frame in special.items():
        for item in frame.to_dict("records"):
            entity_id = normalize_team(item["entity_id"]) if position == "DST" else str(item["entity_id"])
            add((position, int(item["season"]), int(item["week"]), entity_id, normalize_team(item["team"])),
                item.get("fantasy_points"))

    results = []
    changed = 0
    for row in rows:
        game = games_by_week[row["week"]].get(row["team"])
        if not game:
            continue
        opponent, kickoff, source = game
        # Wait until the following day and require published game scores. This is
        # deliberately not live scoring: incomplete games/stat feeds stay pending.
        if opponent != row["opponent_team"] or now < kickoff + timedelta(hours=12):
            continue
        if automatic and now < next_morning(kickoff):
            continue
        if any(datetime.fromisoformat(row[key]) >= kickoff for key in ("recorded_at", "generated_at")):
            continue
        if any(pd.isna(source.get(key)) for key in ("home_score", "away_score", "result")):
            continue
        key = (row["position"], season, row["week"], row["player_id"], row["team"])
        if key in duplicates or key not in actuals:
            continue  # Missing stats are not evidence of a zero-point game.
        points = actuals[key]
        changed += row["actual_points"] != points
        results.append(((scope, season, row["week"], row["position"], row["player_id"]), points))
    history.update_actuals(results)
    return {"updated_count": changed, "checked_count": len(results)}


def sync_actuals(history, season, scope, automatic=False):
    rows = history.rows(season, scope)
    if not rows:
        return {"updated_count": 0, "checked_count": 0}
    schedule = nfl.import_schedules([season])
    now = utc_now()
    eligible = []
    for week in {row["week"] for row in rows}:
        games = game_times(schedule, season, week)
        eligible.extend(row for row in rows if row["week"] == week
                        and row["team"] in games
                        and now >= games[row["team"]][1] + timedelta(hours=12)
                        and (not automatic or now >= next_morning(games[row["team"]][1]))
                        and all(pd.notna(games[row["team"]][2].get(key))
                                for key in ("home_score", "away_score", "result")))
    if not eligible:
        return {"updated_count": 0, "checked_count": 0}
    positions = {row["position"] for row in eligible}
    weekly = (NFLData([season])._load_weekly_player_data()
              if positions & {"QB", "RB", "WR", "TE"} else pd.DataFrame())
    special = load_special_teams_weekly([season]) if positions & {"K", "DST"} else {}
    return reconcile(history, season, scope, schedule, weekly, special, now=now, automatic=automatic)
