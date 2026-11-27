from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from filelock import FileLock
import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.preprocessing import StandardScaler

from main import app
from app.services import model_registry as registry, retraining as training, retraining_worker as worker_module
from app.services.retraining import chronological_plan, latest_complete_week, promotion_decision, make_datasets, stats_ready
from app.services.retraining_worker import RetrainingWorker, schedule_slot, read_status
from app.services.pytorch_projection_model import PyTorchProjectionModel
from app.scripts.train_special_teams import scaler_state

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 11, tzinfo=UTC)  # Tuesday after the scheduled 5 a.m. Toronto check.


def test_plan_separates_training_early_stopping_calibration_and_evaluation():
    assert chronological_plan(10) is None
    plan = chronological_plan(11)
    assert plan == {"train_through": 1, "validation": [2, 3], "calibration": [4, 5, 6, 7], "evaluation": [8, 9, 10, 11]}
    assert plan["train_through"] < min(plan["validation"]) <= max(plan["validation"]) < min(plan["calibration"])
    assert max(plan["calibration"]) < min(plan["evaluation"])


def test_whole_week_must_be_finished_with_known_kickoffs_and_published_scores():
    games = pd.DataFrame([dict(season=2026, week=week, game_type="REG", home_team="BUF", away_team="MIA",
        gameday=f"2026-09-{week + 10:02}", gametime="13:00", home_score=20, away_score=10) for week in (1, 2)])
    assert latest_complete_week(games, 2026, NOW) == 2
    games.loc[1, "away_score"] = np.nan
    assert latest_complete_week(games, 2026, NOW) == 1
    games.loc[1, "away_score"] = 10
    games.loc[1, "gametime"] = None
    assert latest_complete_week(games, 2026, NOW) == 1


def test_weekly_schedule_tracks_toronto_daylight_saving():
    slot, next_slot = schedule_slot(NOW)
    assert slot == datetime(2026, 11, 24, 10, tzinfo=UTC)
    assert next_slot == slot + timedelta(days=7)
    summer, _ = schedule_slot(datetime(2026, 7, 7, 10, tzinfo=UTC))
    assert summer.hour == 9
    previous, upcoming = schedule_slot(datetime(2026, 11, 24, 9, 59, tzinfo=UTC))
    assert previous == datetime(2026, 11, 17, 10, tzinfo=UTC)
    assert upcoming == slot


def test_monday_game_is_eligible_by_tuesday_five_without_a_twelve_hour_wait():
    games = pd.DataFrame([dict(season=2026, week=1, game_type="REG", home_team="BUF", away_team="MIA",
        gameday="2026-11-23", gametime="20:15", home_score=20, away_score=10)])
    assert latest_complete_week(games, 2026, datetime(2026, 11, 24, 10, tzinfo=UTC)) == 1
    assert latest_complete_week(games, 2026, datetime(2026, 11, 24, 9, 14, tzinfo=UTC)) == 0


def test_published_stats_must_cover_both_teams_in_the_correct_week_and_season():
    games = pd.DataFrame([dict(season=2026, week=12, game_type="REG", home_team="BUF", away_team="MIA",
        gameday="2026-11-30", gametime="20:15", home_score=20, away_score=10)])
    players = pd.DataFrame([dict(season=2026, week=12, recent_team=team) for team in ("BUF", "MIA")])
    defenses = pd.DataFrame([dict(season=2026, week=12, team=team) for team in ("BUF", "MIA")])
    assert stats_ready({"players": players, "DST": defenses}, games, 2026, 12)
    assert not stats_ready({"players": players.iloc[:1], "DST": defenses}, games, 2026, 12)
    assert not stats_ready({"players": players, "DST": defenses.assign(week=11)}, games, 2026, 12)
    assert not stats_ready({"players": players.assign(season=2025), "DST": defenses}, games, 2026, 12)
    assert not stats_ready({}, games, 2026, 12)


def test_gate_needs_meaningful_paired_improvement_baseline_bias_and_ranges():
    actual = np.tile([8., 12.], 100)
    old, new, rolling = actual + 2, actual + 1, actual + 3
    fitted = {"ready": True, "validation_coverage": .8}
    assert promotion_decision(actual, new, old, rolling, fitted)["promote"]
    for candidate, incumbent, baseline, ranges in [
        (actual + 1.95, old, rolling, fitted), (actual + 3, old, rolling, fitted),
        (new, old, actual + .5, fitted), (new, old, rolling, {"ready": False}),
        (new, old, rolling, {"ready": True, "validation_coverage": 1.0}),
        (np.full(200, np.nan), old, rolling, fitted),
        (actual + 1, actual + np.tile([-2, 2], 100), rolling, fitted),
    ]:
        assert not promotion_decision(actual, candidate, incumbent, baseline, ranges)["promote"]
    assert not promotion_decision(actual[:10], new[:10], old[:10], rolling[:10], fitted)["promote"]


@pytest.fixture
def base_models(tmp_path, monkeypatch):
    base = tmp_path / "bundled"
    base.mkdir()
    monkeypatch.setattr(registry, "BASE_MODELS", base)
    for position, version in registry.SELECTED_PYTORCH_MODEL_VERSIONS.items():
        (base / f"{position}_model_v{version}.pth").write_bytes(b"bundled-" + position.encode())
    return base


def candidate(position, label):
    root = registry.runs_directory() / "runs" / label / position
    root.mkdir(parents=True)
    checkpoint, ranges = root / "model.pth", root / "ranges.json"
    checkpoint.write_bytes(label.encode())
    ranges.write_text('{"format_version":1}')
    return checkpoint, ranges


def test_atomic_promotion_rollback_checksums_and_concurrent_model_changes(base_models):
    old = registry.selected_model_path("QB")
    old_bytes = old.read_bytes()
    expected = sha256(old_bytes).hexdigest()
    first, ranges = candidate("QB", "first")
    registry.promote("QB", first, ranges, expected_incumbent=expected, report={"count": 100})
    assert registry.selected_model_path("QB") == first
    assert old.read_bytes() == old_bytes
    assert registry.selected_model_path("RB").parent == base_models
    second, second_ranges = candidate("QB", "second")
    with pytest.raises(ValueError, match="changed during evaluation"):
        registry.promote("QB", second, second_ranges, expected_incumbent=expected, report={})
    registry.promote("QB", second, second_ranges, expected_incumbent=sha256(first.read_bytes()).hexdigest(), report={})
    registry.rollback("QB")
    assert registry.selected_model_path("QB") == first
    registry.rollback("QB")
    assert registry.selected_model_path("QB") == old
    assert first.exists() and second.exists()


def test_manifest_rejects_external_paths_and_corrupted_artifacts(base_models):
    with pytest.raises(ValueError):
        registry.artifact_path("../../outside.pth")
    checkpoint, ranges = candidate("QB", "test")
    registry.promote("QB", checkpoint, ranges,
        expected_incumbent=sha256(registry.selected_model_path("QB").read_bytes()).hexdigest(), report={})
    checkpoint.write_bytes(b"corrupt-data")
    with pytest.raises(ValueError, match="checksum"):
        registry.selected_model_path("QB")


def test_promotion_switches_ranges_and_registry_without_changing_saved_history(base_models, monkeypatch):
    from app.services import projection_registry, projection_ranges
    from app.services.prediction_history import prediction_history
    from test_prediction_history import record
    record(monkeypatch)
    before = prediction_history.rows(2026, "espn:123")
    factory = Mock(side_effect=lambda **_: object())
    monkeypatch.setattr(projection_registry, "WeeklyProjectionService", factory)
    services = projection_registry.ProjectionServiceRegistry()
    old = services.get(2026)
    checkpoint, ranges = candidate("QB", "range-ready")
    digest = sha256(checkpoint.read_bytes()).hexdigest()
    registry.atomic_json(ranges, {"format_version": 1, "season": 2026, "positions": {"QB": {
        "checkpoint_sha256": digest, "methods": {"model": {"ready": True, "low_offset": -3,
            "high_offset": 6, "validation_coverage": .8, "validation_count": 100}}}}})
    registry.promote("QB", checkpoint, ranges,
        expected_incumbent=sha256(registry.selected_model_path("QB").read_bytes()).hexdigest(), report={})
    assert services.get(2026) is not old
    bounds = projection_ranges.estimate_range(20, "QB", "model", {"QB": digest})
    assert bounds["floor_points"] == 17 and bounds["ceiling_points"] == 26
    assert prediction_history.rows(2026, "espn:123") == before
    registry.rollback("QB")
    assert registry.manifest()["positions"] == {}


def test_corrupt_manifest_does_not_silently_replace_models(base_models):
    path = registry.runs_directory() / "active.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"format_version":0}')
    with pytest.raises(ValueError):
        registry.selected_model_path("QB")


def special_frames():
    rows = [dict(entity_id=str(entity), entity_name=f"K {entity}", team="BUF", opponent_team="MIA",
                 season=season, week=week, fantasy_points=float(8 + week % 3))
            for entity in range(32) for season in (2025, 2026) for week in range(1, 19)]
    frame = pd.DataFrame(rows)
    return {"K": frame, "DST": frame.copy()}


def checkpoint(position="K"):
    model = PyTorchProjectionModel(2, 1, hidden_size=4, num_layers=1, dropout=0)
    seq = StandardScaler().fit([[0., 0.], [30., 18.]])
    matchup = StandardScaler().fit([[0.], [30.]])
    return dict(format_version=2, model_state_dict=model.state_dict(), sequence_scaler=scaler_state(seq),
        matchup_scaler=scaler_state(matchup), feature_cols=["fantasy_points" if position == "K" else "fantasy_points_ppr", "week"],
        matchup_feature_cols=["allowed" if position == "K" else "passing_yards_allowed"],
        matchup_sources={"allowed": "fantasy_points"}, sequence_length=5, position=position, version=1 if position == "K" else 4,
        model_config=dict(hidden_size=4, num_layers=1, dropout=0), train_seasons=[2023], validation_seasons=[2024], test_seasons=[2025])


def test_training_scalers_and_target_splits_do_not_see_later_weeks():
    frames = special_frames()
    plan = chronological_plan(11)
    train, holdout, indices = make_datasets(frames, checkpoint(), 2026, plan)
    changed = {key: value.copy() for key, value in frames.items()}
    for frame in changed.values():
        frame.loc[(frame.season == 2026) & (frame.week > 1), "fantasy_points"] = 9999
    changed_train, _, _ = make_datasets(changed, checkpoint(), 2026, plan)
    np.testing.assert_array_equal(train.scaler.mean_, changed_train.scaler.mean_)
    assert all(row["season"] < 2026 or row["week"] <= 1 for row in train.sample_metadata)
    for group in ("validation", "calibration", "evaluation"):
        assert {holdout.sample_metadata[index]["week"] for index in indices[group]} == set(plan[group])


def test_pinned_checkpoints_keep_position_and_version_validation(tmp_path):
    from app.services.pytorch_projection_model import load_selected_projection_checkpoint
    path = tmp_path / "pinned.pth"
    saved = checkpoint()
    torch.save(saved, path)
    assert load_selected_projection_checkpoint("K", device=torch.device("cpu"), checkpoint_path=path)[3]["position"] == "K"
    with pytest.raises(ValueError, match="metadata"):
        load_selected_projection_checkpoint("QB", device=torch.device("cpu"), checkpoint_path=path)
    saved["version"] = 999
    torch.save(saved, path)
    with pytest.raises(ValueError, match="metadata"):
        load_selected_projection_checkpoint("K", device=torch.device("cpu"), checkpoint_path=path)


def offense_frames():
    from app.services.player_sequence_dataset import PLAYER_COLS
    from app.config.model_config import DEFENSE_STAT_COLS
    players = []
    defense = []
    for season in (2025, 2026):
        for week in range(1, 19):
            defense.append({**{name: 10. for name in DEFENSE_STAT_COLS}, "opponent_team": "MIA",
                            "season": season, "week": week, "position": "QB"})
            for entity in range(32):
                players.append({**{name: 0. for name in PLAYER_COLS}, "player_id": str(entity),
                    "player_name": f"QB {entity}", "position": "QB", "recent_team": "BUF", "opponent_team": "MIA",
                    "season": season, "week": week, "season_type": "REG", "fantasy_points_ppr": float(10 + week % 3)})
    return {"players": pd.DataFrame(players), "defense": pd.DataFrame(defense), "injuries": pd.DataFrame()}


@pytest.mark.parametrize("position", ["K", "QB"])
def test_real_cpu_training_saves_loadable_candidate_and_never_overwrites_incumbent(base_models, monkeypatch, position):
    monkeypatch.setenv("FANTASY_TRAINING_EPOCHS", "1")
    monkeypatch.setenv("FANTASY_TRAINING_DEVICE", "cpu")
    path = registry.selected_model_path(position)
    torch.save(checkpoint(position), path)
    before = path.read_bytes()
    destination = registry.runs_directory() / "runs/smoke" / position
    old_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        result = training.train_position(position, special_frames() if position == "K" else offense_frames(),
                                         2026, chronological_plan(11), destination)
    finally:
        torch.set_num_threads(old_threads)
    assert (destination / "model.pth").is_file() and (destination / "evaluation.json").is_file()
    saved = torch.load(destination / "model.pth", weights_only=True)
    assert saved["training_cutoff"] == [2026, 1]
    assert result["count"] == 128
    assert path.read_bytes() == before


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("FANTASY_RETRAIN_ENABLED", "true")
    monkeypatch.setattr(worker_module.nfl, "import_schedules", Mock(return_value=pd.DataFrame()))
    monkeypatch.setattr(worker_module, "latest_complete_week", lambda *_: 11)
    monkeypatch.setattr(worker_module, "training_frames", Mock(return_value={}))
    monkeypatch.setattr(worker_module, "stats_ready", Mock(return_value=True))
    monkeypatch.setattr(worker_module, "train_position", Mock(return_value={"promote": False, "reason": "Current model is better"}))
    return RetrainingWorker(clock=lambda: NOW)


def test_schedule_runs_once_per_new_completed_week_across_restart(worker, monkeypatch):
    worker.run_once()
    assert worker_module.train_position.call_count == 6
    assert read_status()["state"] == "complete"
    RetrainingWorker(clock=lambda: NOW + timedelta(minutes=2)).run_once()
    assert worker_module.train_position.call_count == 6
    # A following scheduled week with no new completed games does not retrain.
    worker.clock = lambda: NOW + timedelta(days=7)
    worker.run_once()
    assert worker_module.train_position.call_count == 6
    worker.clock = lambda: NOW + timedelta(days=14)
    monkeypatch.setattr(worker_module, "latest_complete_week", lambda *_: 12)
    worker.run_once()
    assert worker_module.train_position.call_count == 12


def test_failure_retries_only_failed_positions_and_redacts_errors(worker, caplog):
    def run(position, *args, **kwargs):
        if position == "QB":
            raise ValueError("private-error-detail")
        return {"promote": False}
    worker_module.train_position.side_effect = run
    worker.run_once()
    assert read_status()["state"] == "error"
    worker.clock = lambda: NOW + timedelta(minutes=59)
    worker.run_once()
    assert worker_module.train_position.call_count == 6
    worker_module.train_position.side_effect = None
    worker.clock = lambda: NOW + timedelta(hours=1, minutes=1)
    worker.run_once()
    assert worker_module.train_position.call_count == 7
    assert read_status()["state"] == "complete"
    assert "private-error-detail" not in caplog.text


def test_worker_lock_and_disabled_configuration_prevent_training(worker, monkeypatch):
    root = registry.runs_directory()
    root.mkdir(parents=True)
    with FileLock(str(root / "worker.lock")):
        worker.run_once()
    worker_module.train_position.assert_not_called()
    monkeypatch.setenv("FANTASY_RETRAIN_ENABLED", "false")
    worker.run_once(force=True)
    worker_module.train_position.assert_not_called()


def test_restarted_worker_recovers_interrupted_state_and_resumes_unfinished_positions(worker):
    registry.atomic_json(registry.runs_directory() / "status.json", {
        "state": "running", "data_key": "2026:11", "positions": {"QB": {"promote": False}}})
    worker.run_once()
    assert read_status()["state"] == "error" and "interrupted" in read_status()["last_error"]
    worker_module.train_position.assert_not_called()
    worker.clock = lambda: NOW + timedelta(hours=1, minutes=1)
    worker.run_once()
    assert worker_module.train_position.call_count == 5
    assert read_status()["state"] == "complete"


def test_status_endpoint_never_starts_training(worker):
    client = TestClient(app)
    response = client.get("/api/training/status")
    assert response.status_code == 200 and response.json()["state"] == "waiting"
    worker_module.training_frames.assert_not_called()
    worker_module.train_position.assert_not_called()


def test_tuesday_check_retries_until_monday_results_settle_instead_of_skipping_week(worker, monkeypatch):
    clock = [datetime(2026, 12, 1, 10, tzinfo=UTC)]  # Tuesday 5 a.m. Toronto.
    worker.clock = lambda: clock[0]
    games = pd.DataFrame([dict(season=2026, week=12, game_type="REG", home_team="BUF", away_team="MIA",
        gameday="2026-11-30", gametime="20:15", home_score=20, away_score=10)])
    monkeypatch.setattr(worker_module.nfl, "import_schedules", Mock(return_value=games))
    settled = datetime(2026, 12, 1, 9, 15, tzinfo=UTC)  # Eight hours after Monday kickoff.
    monkeypatch.setattr(worker_module, "latest_complete_week", lambda schedule, season, now: 11 if now < settled else 12)
    registry.atomic_json(registry.runs_directory() / "status.json", {
        "state": "complete", "completed_data_key": "2026:11",
        "last_scheduled_at": "2026-11-24T10:00:00+00:00", "positions": {}})
    monkeypatch.setattr(worker_module, "stats_ready", Mock(return_value=False))
    worker.run_once()
    assert read_status()["state"] == "waiting"
    assert read_status()["last_scheduled_at"] == "2026-11-24T10:00:00+00:00"
    worker_module.train_position.assert_not_called()
    clock[0] += timedelta(hours=1)
    worker.run_once()
    worker_module.train_position.assert_not_called()
    clock[0] = datetime(2026, 12, 1, 12, tzinfo=UTC)
    worker_module.stats_ready.return_value = True
    worker.run_once()
    assert worker_module.train_position.call_count == 6
    assert read_status()["completed_data_key"] == "2026:12"
