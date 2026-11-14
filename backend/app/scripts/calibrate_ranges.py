"""Build floor/ceiling offsets on an unseen season; validate on its later weeks."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from app.config.model_config import SELECTED_PYTORCH_MODEL_VERSIONS
from app.services.data_snapshot import FrameSnapshot
from app.services.disk_cache import disk_cache
from app.services.NFL_data import NFLData
from app.services.projection_ranges import RANGE_PATH, checkpoint_hashes, fit_residual_range
from app.services.projection_slate import project_position_slate
from app.services.projection_types import PlayerProjectionRequest
from app.services.pytorch_inference import PyTorchProjectionService
from app.services.special_teams_data import load_special_teams_weekly
from app.services.special_teams_inference import SpecialTeamsProjectionService


def cached_frames(namespace, names, season):
    # Completed-season stats can be reused even after the disposable cache TTL.
    if not disk_cache.path.is_file():
        return None
    with sqlite3.connect(disk_cache.path) as connection:
        for (payload,) in connection.execute(
                "SELECT payload FROM entries WHERE namespace=? ORDER BY accessed DESC", (namespace,)):
            snapshot = FrameSnapshot(payload)
            if not set(names).issubset(snapshot.names):
                continue
            frames = {name: snapshot[name] for name in names}
            if all(season in frame.season.unique() for frame in frames.values()):
                return {name: frame[frame.season == season].copy() for name, frame in frames.items()}
    return None


def calibrate(season, split_week, output):
    offense = cached_frames("nfl_data", ("player_features", "defense_features"), season)
    if offense is None:
        data = NFLData([season])
        data.load_data()
        offense = {"player_features": data.get_player_stats(), "defense_features": data.get_defense_stats()}
    special = cached_frames("special_teams", ("K", "DST"), season)
    if special is None:
        special = load_special_teams_weekly([season])
    hashes = checkpoint_hashes()
    artifact = {"format_version": 1, "season": season, "calibration_through_week": split_week,
                "created_at": datetime.now(timezone.utc).isoformat(), "positions": {}}
    for position in SELECTED_PYTORCH_MODEL_VERSIONS:
        if position in {"K", "DST"}:
            service = SpecialTeamsProjectionService(position, special[position])
            frame = special[position].rename(columns={"entity_id": "player_id", "entity_name": "player_name"})
            points_column = "fantasy_points"
        else:
            service = PyTorchProjectionService(position, offense["player_features"], offense["defense_features"])
            frame = offense["player_features"]
            frame = frame[(frame.position == position) & (frame.season_type == "REG")]
            frame = frame.rename(columns={"recent_team": "team"})
            points_column = "fantasy_points_ppr"
        checkpoint = service.checkpoint
        used_seasons = set(checkpoint.get("train_seasons", []) + checkpoint.get("validation_seasons", [])
                           + checkpoint.get("test_seasons", []))
        if not used_seasons or season <= max(used_seasons):
            raise ValueError(f"{position}: calibration season must follow every saved training/evaluation season")
        if checkpoint_hashes().get(position) != hashes[position]:
            raise ValueError("Checkpoint changed while calibrating")
        frame = frame[(frame.week >= 1) & (frame.week <= 18)].drop_duplicates(["player_id", "season", "week"])
        actual = {(str(row.player_id), int(row.week)): float(getattr(row, points_column))
                  for row in frame.itertuples(index=False)}
        requests = [PlayerProjectionRequest(player_id=str(row.player_id), player_name=str(row.player_name),
                    team=str(row.team), opponent_team=str(row.opponent_team),
                    season=season, upcoming_week=int(row.week)) for row in frame.itertuples(index=False)]
        residuals = {}
        for start in range(0, len(requests), 512):
            result = project_position_slate(service, requests[start:start + 512])
            for projection in result.projections:
                item = projection.request
                group = residuals.setdefault(projection.projection_method, {"calibration": [], "validation": []})
                group["calibration" if item.upcoming_week <= split_week else "validation"].append(
                    actual[item.player_id, item.upcoming_week] - projection.predicted_points)
        methods = {method: fit_residual_range(values["calibration"], values["validation"])
                   for method, values in residuals.items()}
        artifact["positions"][position] = {"checkpoint_sha256": hashes[position], "methods": methods}
        print(position, json.dumps(methods), flush=True)
    if hashes != checkpoint_hashes():
        raise ValueError("Checkpoint files changed; rerun calibration")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(artifact, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"Saved calibrated ranges: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--split-week", type=int, default=12)
    parser.add_argument("--output", type=Path, default=RANGE_PATH)
    arguments = parser.parse_args()
    if not 6 <= arguments.split_week <= 14:
        parser.error("--split-week must be between 6 and 14")
    calibrate(arguments.season, arguments.split_week, arguments.output)
