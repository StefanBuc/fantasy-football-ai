"""Durable pregame predictions. This database is never expired or cache-pruned."""

from contextlib import contextmanager
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sqlite3

import pandas as pd

from app.config.model_config import SELECTED_PYTORCH_MODEL_VERSIONS
from app.services.performance import logger
from app.services.projection_ranges import estimate_range
from app.services.espn_benchmark import ESPN_SCORING
from app.services.accuracy_insights import insights, range_result, paired


SCORING = "Full PPR for QB/RB/WR/TE; app K/DST scoring (not custom ESPN scoring)."


def utc_now():
    return datetime.now(timezone.utc)


def normalize_team(team):
    value = str(team or "").upper().removeprefix("TEAM:")
    return {"LAR": "LA", "WSH": "WAS"}.get(value, value)


def game_times(schedule, season, week):
    """nflverse gameday/gametime are Eastern time, including overseas games."""
    required = {"season", "week", "home_team", "away_team", "gameday", "gametime"}
    if schedule is None or not required.issubset(schedule.columns):
        return {}
    games = schedule[(schedule.season == season) & (schedule.week == week)]
    if "game_type" in games:
        games = games[games.game_type == "REG"]
    result = {}
    for game in games.to_dict("records"):
        try:
            kickoff = pd.Timestamp(f"{game['gameday']} {game['gametime']}")
            if pd.isna(kickoff):
                continue
            kickoff = kickoff.tz_localize("America/New_York").tz_convert("UTC").to_pydatetime()
        except (ValueError, TypeError):
            continue  # Unknown kickoff: never guess whether a prediction is pregame.
        home, away = normalize_team(game["home_team"]), normalize_team(game["away_team"])
        result[home] = (away, kickoff, game)
        result[away] = (home, kickoff, game)
    return result


class PredictionHistory:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("""CREATE TABLE IF NOT EXISTS predictions (
                scope TEXT NOT NULL, season INTEGER NOT NULL, week INTEGER NOT NULL,
                player_id TEXT NOT NULL, player_name TEXT, position TEXT NOT NULL,
                team TEXT NOT NULL, opponent_team TEXT NOT NULL,
                predicted_points REAL NOT NULL, projection_method TEXT NOT NULL,
                model_version TEXT NOT NULL, model_revision TEXT NOT NULL,
                generated_at TEXT NOT NULL, recorded_at TEXT NOT NULL, kickoff TEXT NOT NULL,
                actual_points REAL, actual_updated_at TEXT,
                PRIMARY KEY(scope, season, week, position, player_id)
            )""")
            range_columns = {"floor_points": "REAL", "ceiling_points": "REAL",
                             "range_note": "TEXT", "range_revision": "TEXT",
                             "espn_predicted_points": "REAL", "espn_scoring": "TEXT", "espn_recorded_at": "TEXT"}
            existing = {row[1] for row in connection.execute("PRAGMA table_info(predictions)")}
            if not set(range_columns).issubset(existing):
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    existing = {row[1] for row in connection.execute("PRAGMA table_info(predictions)")}
                    for name, kind in range_columns.items():
                        if name not in existing:
                            connection.execute(f"ALTER TABLE predictions ADD COLUMN {name} {kind}")
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, *, season, week, samples, schedule, generated_at,
               model_revision, scope="weekly", model_hashes=None):
        games = game_times(schedule, season, week)
        if not games or generated_at.tzinfo is None:
            return 0
        # Take the clock after acquiring the write lock, not before waiting for it.
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            now = utc_now()
            generated_at = generated_at.astimezone(timezone.utc)
            if generated_at > now:
                return 0
            saved = 0
            for sample in samples:
                position = sample["position"].upper().replace("D/ST", "DST")
                player_id = sample.get("player_id")
                points = sample.get("predicted_points")
                team = normalize_team(sample.get("team"))
                game = games.get(team)
                if (not player_id or position not in SELECTED_PYTORCH_MODEL_VERSIONS
                        or points is None or not math.isfinite(points) or game is None):
                    continue
                opponent, kickoff, _ = game
                if (now >= kickoff or generated_at >= kickoff
                        or normalize_team(sample.get("opponent_team")) != opponent):
                    continue
                if position == "DST":
                    player_id = normalize_team(player_id)
                bounds = estimate_range(points, position, sample.get("projection_method") or "model", model_hashes or {})
                if sample.get("is_on_bye") or sample.get("availability") == "unavailable":
                    bounds.update(floor_points=None, ceiling_points=None,
                                  range_note="Range unavailable for an availability-adjusted projection.")
                espn_points = sample.get("espn_predicted_points")
                has_espn = (sample.get("espn_scoring") == ESPN_SCORING and isinstance(espn_points, (int, float))
                            and math.isfinite(espn_points) and position in {"QB", "RB", "WR", "TE"})
                if has_espn:
                    # A cached AI generation may be older than the archived AI.
                    # Preserve that AI forecast but still capture a fresh ESPN observation.
                    connection.execute("""UPDATE predictions SET espn_predicted_points=?,espn_scoring=?,espn_recorded_at=?
                        WHERE scope=? AND season=? AND week=? AND position=? AND player_id=?
                            AND team=? AND opponent_team=? AND kickoff=? AND kickoff>?
                            AND actual_points IS NULL AND (espn_recorded_at IS NULL OR espn_recorded_at<=?)""",
                        (float(espn_points), ESPN_SCORING, now.isoformat(), scope, season, week, position, str(player_id),
                         team, opponent, kickoff.isoformat(), now.isoformat(), now.isoformat()))
                values = (
                    scope, season, week, str(player_id), sample.get("player_name"), position,
                    team, opponent, float(points), sample.get("projection_method") or "model",
                    f"{position}_model_v{SELECTED_PYTORCH_MODEL_VERSIONS[position]}",
                    model_revision, generated_at.isoformat(), now.isoformat(), kickoff.isoformat(),
                    bounds["floor_points"], bounds["ceiling_points"], bounds["range_note"], bounds["range_revision"],
                    float(espn_points) if has_espn else None, ESPN_SCORING if has_espn else None,
                    now.isoformat() if has_espn else None,
                )
                cursor = connection.execute("""INSERT INTO predictions (
                    scope, season, week, player_id, player_name, position, team, opponent_team,
                    predicted_points, projection_method, model_version, model_revision,
                    generated_at, recorded_at, kickoff, floor_points, ceiling_points, range_note, range_revision,
                    espn_predicted_points, espn_scoring, espn_recorded_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(scope,season,week,position,player_id) DO UPDATE SET
                        player_name=excluded.player_name, team=excluded.team,
                        opponent_team=excluded.opponent_team,
                        predicted_points=excluded.predicted_points,
                        projection_method=excluded.projection_method,
                        model_version=excluded.model_version, model_revision=excluded.model_revision,
                        generated_at=excluded.generated_at, recorded_at=excluded.recorded_at,
                        kickoff=excluded.kickoff, floor_points=excluded.floor_points,
                        ceiling_points=excluded.ceiling_points, range_note=excluded.range_note,
                        range_revision=excluded.range_revision,
                        espn_predicted_points=CASE WHEN predictions.team=excluded.team AND predictions.opponent_team=excluded.opponent_team
                            AND predictions.kickoff=excluded.kickoff THEN predictions.espn_predicted_points ELSE excluded.espn_predicted_points END,
                        espn_scoring=CASE WHEN predictions.team=excluded.team AND predictions.opponent_team=excluded.opponent_team
                            AND predictions.kickoff=excluded.kickoff THEN predictions.espn_scoring ELSE excluded.espn_scoring END,
                        espn_recorded_at=CASE WHEN predictions.team=excluded.team AND predictions.opponent_team=excluded.opponent_team
                            AND predictions.kickoff=excluded.kickoff THEN predictions.espn_recorded_at ELSE excluded.espn_recorded_at END
                    WHERE predictions.kickoff > excluded.recorded_at
                        AND predictions.generated_at <= excluded.generated_at
                        AND predictions.actual_points IS NULL""", values)
                saved += cursor.rowcount
            return saved

    def rows(self, season, scope):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM predictions WHERE season=? AND scope=? ORDER BY week DESC, position, player_id",
                (season, scope),
            )]

    def week_records(self, season, week, scope):
        with self.connect() as connection:
            return {(row["position"], row["player_id"]): dict(row) for row in connection.execute(
                "SELECT * FROM predictions WHERE season=? AND week=? AND scope=?", (season, week, scope))}

    def update_actuals(self, results):
        with self.connect() as connection:
            for key, points in results:
                connection.execute("""UPDATE predictions SET actual_points=?, actual_updated_at=?
                    WHERE scope=? AND season=? AND week=? AND position=? AND player_id=?""",
                    (points, utc_now().isoformat(), *key))

    def report(self, season, scope, week=None, position=None, limit=100, offset=0):
        rows = self.rows(season, scope)
        trend_rows = [row for row in rows if position is None or row["position"] == position]
        filtered = [row for row in trend_rows if week is None or row["week"] == week]

        def metrics(items):
            errors = [row["predicted_points"] - row["actual_points"]
                      for row in items if row["actual_points"] is not None]
            return {"saved": len(items), "scored": len(errors), "pending": len(items) - len(errors),
                    "mae": sum(abs(error) for error in errors) / len(errors) if errors else None,
                    "bias": sum(errors) / len(errors) if errors else None}

        for row in filtered:
            row["error"] = (row["predicted_points"] - row["actual_points"]
                            if row["actual_points"] is not None else None)
            row["range_result"] = range_result(row)
            row["espn_error"] = row["espn_predicted_points"] - row["actual_points"] if paired(row) and row["actual_points"] is not None else None
        return {
            "season": season, "scoring": SCORING, "summary": metrics(filtered),
            **insights(filtered),
            "by_position": [{"position": value, **metrics([row for row in filtered if row["position"] == value])}
                            for value in ("QB", "RB", "WR", "TE", "K", "DST")],
            "by_model": [{"model_version": version, "model_revision": revision, "projection_method": method,
                          **metrics([row for row in filtered if
                                     (row["model_version"], row["model_revision"], row["projection_method"])
                                     == (version, revision, method)])}
                         for version, revision, method in sorted({
                             (row["model_version"], row["model_revision"], row["projection_method"])
                             for row in filtered})],
            "weekly_trend": [{"week": value, **metrics([row for row in trend_rows if row["week"] == value])}
                             for value in sorted({row["week"] for row in trend_rows})],
            "records": filtered[offset:offset + limit], "limit": limit, "offset": offset,
        }


prediction_history = PredictionHistory(Path(os.environ.get(
    "FANTASY_HISTORY_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "predictions.sqlite3"),
)))


def record_predictions(service, *, season, week, samples, generated_at, scope="weekly",
                       strict=False, schedule=None):
    """History failure should not hide usable projections; reads surface DB errors."""
    if not samples:
        return 0
    try:
        return prediction_history.record(
            season=season, week=week, samples=samples,
            schedule=(schedule if schedule is not None else
                      getattr(getattr(service, "data", None), "schedule", None)), generated_at=generated_at,
            model_revision=getattr(service, "model_revision", "unknown"), scope=scope,
            model_hashes=getattr(service, "model_hashes", {}),
        )
    except (OSError, sqlite3.Error) as error:
        if strict:
            raise
        logger.warning("Cannot save prediction history: %s", error)
        return 0
