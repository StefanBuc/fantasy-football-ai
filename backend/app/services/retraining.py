"""Chronological challenger training. Forecast history is never training input or rewritten."""

import copy
from datetime import timedelta
from hashlib import sha256
import math
import os
import random

import torch
import numpy as np
import pandas as pd

from app.services.model_registry import atomic_json, selected_model_path, promote
from app.services.pytorch_projection_model import (
    PyTorchProjectionModel, load_projection_checkpoint, inference_device,
)
from app.services.player_sequence_dataset import PlayerSequenceDataset
from app.services.special_teams_sequence_dataset import SpecialTeamsSequenceDataset
from app.services.projection_ranges import fit_residual_range
from app.services.prediction_history import game_times, normalize_team
from app.scripts.train_special_teams import run_epoch, scaler_state


def latest_complete_week(schedule, season, now):
    required = {"season", "week", "game_type", "home_score", "away_score"}
    if schedule is None or not required.issubset(schedule.columns):
        return 0
    last = 0
    for week in range(1, 19):
        games = schedule[(schedule.season == season) & (schedule.week == week) & (schedule.game_type == "REG")]
        times = game_times(schedule, season, week)
        if (games.empty or games[["home_score", "away_score"]].isna().any().any()
                or len(times) != 2 * len(games) or any(now < kickoff + timedelta(hours=8) for _, kickoff, _ in times.values())):
            break
        last = week
    return last


def stats_ready(frames, schedule, season, week):
    expected = set(game_times(schedule, season, week))
    if not expected:
        return False
    for name, team_column in (("players", "recent_team"), ("DST", "team")):
        frame = frames.get(name)
        if frame is None or not {"season", "week", team_column}.issubset(frame.columns):
            return False
        available = frame.loc[(frame.season == season) & (frame.week == week), team_column]
        if not expected.issubset({normalize_team(team) for team in available}):
            return False
    return True


def chronological_plan(last_week):
    if last_week < 11:
        return None  # Need current-season training plus disjoint validation/calibration/evaluation.
    return {"train_through": last_week - 10,
            "validation": list(range(last_week - 9, last_week - 7)),
            "calibration": list(range(last_week - 7, last_week - 3)),
            "evaluation": list(range(last_week - 3, last_week + 1))}


def before_cutoff(frame, season, week):
    return frame[(frame.season < season) | ((frame.season == season) & (frame.week <= week))].copy()


def training_frames(season, check_cancelled=lambda: None):
    """Cache aggregated tables by season; never retain multi-season play-by-play in RAM."""
    from app.services.NFL_data import NFLData
    from app.services.special_teams_data import load_special_teams_weekly
    from app.services.data_snapshot import source_fingerprint, encode_frames, decode_frames
    from app.services.disk_cache import disk_cache

    groups = {name: [] for name in ("players", "defense", "injuries", "K", "DST")}
    fingerprint = source_fingerprint()
    for year in range(max(2020, season - 5), season + 1):
        check_cancelled()
        key = (year, fingerprint)
        payload = disk_cache.get("training_tables", key)
        frames = None
        if payload is not None:
            try:
                frames, _ = decode_frames(payload)
                if not set(groups).issubset(frames):
                    frames = None
            except Exception:
                frames = None
        if frames is None:
            data = NFLData([year])
            data.load_data()
            check_cancelled()
            data.load_injuries()
            special = load_special_teams_weekly([year])
            check_cancelled()
            frames = {"players": data.get_player_stats(), "defense": data.get_defense_stats(),
                      "injuries": data.injuries, **special}
            disk_cache.put("training_tables", key, encode_frames(frames, {}),
                           ttl_seconds=3600 if year == season else 365 * 86400, max_entries=12)
        for name in groups:
            groups[name].append(frames[name])
    return {name: pd.concat(frames, ignore_index=True) for name, frames in groups.items()}


def make_datasets(frames, checkpoint, season, plan):
    train = {name: before_cutoff(frame, season, plan["train_through"]) if not frame.empty else frame
             for name, frame in frames.items()}
    full = {name: before_cutoff(frame, season, max(plan["evaluation"])) if not frame.empty else frame
            for name, frame in frames.items()}
    position = checkpoint["position"]

    def build(data, scalers=None, target_seasons=None):
        common = dict(feature_cols=checkpoint["feature_cols"], sequence_length=checkpoint["sequence_length"],
                      target_seasons=target_seasons)
        if scalers:
            common.update(scaler=scalers[0], matchup_scaler=scalers[1])
        if position in {"K", "DST"}:
            return SpecialTeamsSequenceDataset(data[position], matchup_sources=checkpoint["matchup_sources"], **common)
        return PlayerSequenceDataset(data["players"], data["defense"], position=position,
                                     injury_df=data["injuries"], matchup_feature_cols=checkpoint["matchup_feature_cols"], **common)

    training = build(train)
    holdout = build(full, (training.scaler, training.matchup_scaler), [season])
    indices = {group: [index for index, row in enumerate(holdout.sample_metadata) if row["week"] in plan[group]]
               for group in ("validation", "calibration", "evaluation")}
    return training, holdout, indices


def paired_predictions(model, checkpoint, sequence_scaler, matchup_scaler, dataset, indices, device):
    """Identical examples for both models, transformed with each model's own training scalers."""
    if (list(dataset.feature_cols) != checkpoint["feature_cols"]
            or list(dataset.matchup_feature_cols) != checkpoint["matchup_feature_cols"]
            or dataset.sequences.shape[1] != checkpoint["sequence_length"]):
        raise ValueError("Evaluation feature schema does not match the checkpoint")
    predictions = []
    for start in range(0, len(indices), 128):
        batch = indices[start:start + 128]
        sequences = dataset.sequences[batch].numpy()
        count, length, features = sequences.shape
        raw = dataset.scaler.inverse_transform(sequences.reshape(-1, features))
        sequences = sequence_scaler.transform(raw).reshape(count, length, features)
        raw_matchup = dataset.matchup_scaler.inverse_transform(dataset.matchups[batch].numpy())
        matchups = matchup_scaler.transform(raw_matchup)
        with torch.inference_mode():
            output = model(torch.tensor(sequences, dtype=torch.float32, device=device),
                           torch.tensor(matchups, dtype=torch.float32, device=device))
        predictions.extend(output.detach().cpu().numpy().reshape(-1).tolist())
    return np.asarray(predictions, dtype=float)


def promotion_decision(actual, challenger, incumbent, rolling, fitted, *, min_samples=100,
                       min_absolute=.1, min_relative=.02):
    arrays = [np.asarray(values, dtype=float) for values in (actual, challenger, incumbent, rolling)]
    if len(arrays[0]) < min_samples or any(array.shape != arrays[0].shape or not np.isfinite(array).all() for array in arrays):
        return {"promote": False, "reason": "Insufficient or invalid paired evaluation samples."}
    actual, challenger, incumbent, rolling = arrays
    new_mae, old_mae, baseline = [float(np.mean(np.abs(values - actual))) for values in (challenger, incumbent, rolling)]
    improvement = old_mae - new_mae
    bias, old_bias = float(np.mean(challenger - actual)), float(np.mean(incumbent - actual))
    ready = (fitted.get("ready") and .70 <= fitted.get("validation_coverage", 0) <= .95)
    accepted = (improvement >= max(min_absolute, old_mae * min_relative) and new_mae < baseline
                and abs(bias) <= abs(old_bias) + .5 and ready)
    return {"promote": bool(accepted), "reason": "Improved held-out accuracy and validated ranges." if accepted else
            "Accuracy, bias, baseline, or range gate did not pass; current model retained.",
            "count": len(actual), "candidate_mae": new_mae, "incumbent_mae": old_mae,
            "rolling_mae": baseline, "improvement": improvement, "candidate_bias": bias,
            "incumbent_bias": old_bias, "range_ready": bool(ready)}


def train_position(position, frames, season, plan, destination, *, check_cancelled=lambda: None):
    check_cancelled()
    source = selected_model_path(position)
    source_hash = sha256(source.read_bytes()).hexdigest()
    requested = os.getenv("FANTASY_TRAINING_DEVICE", "cpu").lower()
    if requested not in {"cpu", "auto", "cuda"}:
        raise ValueError("FANTASY_TRAINING_DEVICE must be cpu, auto, or cuda")
    device = torch.device("cpu") if requested == "cpu" else inference_device()
    if requested == "cuda" and device.type != "cuda":
        raise RuntimeError("The training CUDA device is unavailable")
    incumbent, incumbent_sequence, incumbent_matchup, checkpoint, _ = load_projection_checkpoint(source, device)
    # A saved model's training/selection data must precede this evaluation.
    cutoff = checkpoint.get("training_cutoff")
    if cutoff and tuple(cutoff) >= (season, min(plan["evaluation"])):
        raise ValueError("Incumbent training overlaps this evaluation window")
    if not cutoff and max(checkpoint.get("train_seasons", []) + checkpoint.get("validation_seasons", []) + checkpoint.get("test_seasons", []), default=0) >= season:
        raise ValueError("Incumbent data boundary is not safe for this evaluation season")
    training, holdout, indices = make_datasets(frames, checkpoint, season, plan)
    if len(training) < 200 or len(indices["validation"]) < 40 or len(indices["calibration"]) < 100 or len(indices["evaluation"]) < 100:
        return {"promote": False, "reason": "Not enough published samples for chronological training and evaluation."}
    seed = 42
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model = PyTorchProjectionModel(len(checkpoint["feature_cols"]), len(checkpoint["matchup_feature_cols"]),
                                  **checkpoint["model_config"]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=.001)
    train_loader = torch.utils.data.DataLoader(training, batch_size=64, shuffle=True,
                                              generator=torch.Generator().manual_seed(seed))
    validation_loader = torch.utils.data.DataLoader(torch.utils.data.Subset(holdout, indices["validation"]), batch_size=128)
    best, state, stale, best_epoch = math.inf, None, 0, 0
    epochs = max(1, min(100, int(os.getenv("FANTASY_TRAINING_EPOCHS", "30"))))
    for epoch in range(1, epochs + 1):
        check_cancelled()
        # Check at each batch too, so shutdown/timeout does not wait an entire epoch.
        def batches():
            for batch in train_loader:
                check_cancelled()
                yield batch
        train_error = run_epoch(model, batches(), torch.nn.L1Loss(), device, optimizer)
        validation = run_epoch(model, validation_loader, torch.nn.L1Loss(), device)
        if not math.isfinite(train_error) or not math.isfinite(validation):
            raise ValueError("Training produced a nonfinite loss")
        if validation < best:
            best, state, stale, best_epoch = validation, copy.deepcopy(model.state_dict()), 0, epoch
        else:
            stale += 1
        if stale >= 7:
            break
    if state is None:
        raise ValueError("Training did not produce a candidate")
    model.load_state_dict(state); model.eval()
    new_checkpoint = {**checkpoint, "model_state_dict": {name: value.cpu() for name, value in model.state_dict().items()},
                      "sequence_scaler": scaler_state(training.scaler), "matchup_scaler": scaler_state(training.matchup_scaler),
                      "training_cutoff": [season, plan["train_through"]], "validation_weeks": plan["validation"],
                      "calibration_weeks": plan["calibration"], "evaluation_weeks": plan["evaluation"],
                      "train_seasons": sorted({row["season"] for row in training.sample_metadata}),
                      "validation_seasons": [season], "test_seasons": [season],
                      "best_epoch": best_epoch, "validation_mae": best, "seed": seed}
    predicted = {group: paired_predictions(model, new_checkpoint, training.scaler, training.matchup_scaler,
                                          holdout, indices[group], device) for group in ("calibration", "evaluation")}
    actual = {group: holdout.targets[indices[group]].numpy().reshape(-1) for group in ("calibration", "evaluation")}
    old = paired_predictions(incumbent, checkpoint, incumbent_sequence, incumbent_matchup,
                             holdout, indices["evaluation"], device)
    fitted = fit_residual_range(actual["calibration"] - predicted["calibration"], actual["evaluation"] - predicted["evaluation"])
    sequences = holdout.sequences[indices["evaluation"]].numpy()
    raw = training.scaler.inverse_transform(sequences.reshape(-1, sequences.shape[-1])).reshape(sequences.shape)
    point_column = checkpoint["feature_cols"].index("fantasy_points" if position in {"K", "DST"} else "fantasy_points_ppr")
    rolling = raw[:, :, point_column].mean(axis=1)
    report = promotion_decision(actual["evaluation"], predicted["evaluation"], old, rolling, fitted)
    report.update(position=position, season=season, plan=plan, train_count=len(training), best_epoch=best_epoch,
                  validation_count=len(indices["validation"]), calibration_count=len(indices["calibration"]),
                  device=str(device), incumbent_sha256=source_hash)
    destination.mkdir(parents=True, exist_ok=False)
    new_checkpoint["test_mae"] = report.get("candidate_mae")
    checkpoint_path = destination / "model.pth"
    torch.save(new_checkpoint, checkpoint_path)
    with checkpoint_path.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    # Read back the candidate before it can become active.
    loaded = load_projection_checkpoint(checkpoint_path, torch.device("cpu"))
    assert loaded[3]["position"] == position and loaded[3]["version"] == checkpoint["version"]
    candidate_hash = sha256(checkpoint_path.read_bytes()).hexdigest()
    range_path = destination / "ranges.json"
    atomic_json(range_path, {"format_version": 1, "season": season, "positions": {
        position: {"checkpoint_sha256": candidate_hash, "methods": {"model": fitted}}}})
    atomic_json(destination / "evaluation.json", report)
    check_cancelled()
    if report["promote"]:
        promote(position, checkpoint_path, range_path, expected_incumbent=source_hash, report=report)
    return report
