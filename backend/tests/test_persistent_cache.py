from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pandas as pd
import pytest

from app.services import disk_cache as disk_module
from app.services.data_snapshot import decode_frames, encode_frames
from app.services.disk_cache import DiskCache, disk_cache
from app.services.espn_projection_cache import ESPNLeagueWeekProjection, ESPNProjectionCache
from app.services.projection_types import ProjectionSlateResult
from app.services.result_cache import ResultCache
from app.services import weekly_projection_service as weekly


def test_disk_cache_survives_new_instance_and_expires(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    monkeypatch.setattr(disk_module, "time", lambda: 100.0)
    DiskCache(path).put("test", (2024, "QB"), b"value", ttl_seconds=10)
    assert DiskCache(path).get("test", (2024, "QB")) == b"value"
    monkeypatch.setattr(disk_module, "time", lambda: 110.0)
    assert DiskCache(path).get("test", (2024, "QB")) is None


def test_disk_cache_evicts_oldest_and_clear_is_scoped(tmp_path, monkeypatch):
    cache = DiskCache(tmp_path / "cache.sqlite3")
    for index in range(3):
        monkeypatch.setattr(disk_module, "time", lambda: 100 + index)
        cache.put("test", index, b"value", 100, max_entries=2)
    assert cache.get("test", 0) is None
    assert cache.get("test", 2) == b"value"
    cache.put("other", 1, b"other", 100)
    cache.clear("test")
    assert cache.get("test", 2) is None
    assert cache.get("other", 1) == b"other"


def test_unwritable_disk_cache_degrades_to_miss(tmp_path):
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("file")
    cache = DiskCache(blocker / "cache.sqlite3")
    cache.put("test", 1, b"payload", 10)
    assert cache.get("test", 1) is None


def test_frame_roundtrip_preserves_types_and_nulls():
    frame = pd.DataFrame({
        "id": ["001", None], "mixed_id": pd.Series(["002", 3], dtype="object"),
        "points": pd.Series([1, float("nan")], dtype="float32"),
        "week": [1, 2], "date": pd.to_datetime(["2024-09-01", "2024-09-02"], utc=True),
    })
    frames, metadata = decode_frames(encode_frames({"weekly": frame}, {"generation": "abc"}))
    pd.testing.assert_frame_equal(frames["weekly"], frame)
    assert metadata == {"generation": "abc"}


def test_weekly_projection_survives_restart_and_generation_changes():
    result = ProjectionSlateResult(projections=[], skipped=[])
    first = ResultCache(persistent_key="generation-1")
    assert first.get_or_create((2024, 1, "QB"), lambda: result) == result
    builder = Mock(side_effect=AssertionError("should use disk"))
    restored = ResultCache(persistent_key="generation-1").get_or_create((2024, 1, "QB"), builder)
    assert restored == result
    builder.assert_not_called()
    replacement = ProjectionSlateResult(projections=[], skipped=[])
    assert ResultCache(persistent_key="generation-2").get_or_create(
        (2024, 1, "QB"), lambda: replacement,
    ) == replacement


def test_corrupt_projection_is_rebuilt():
    disk_cache.put("weekly/version", "key", b"not-json", 900)
    result = ProjectionSlateResult(projections=[], skipped=[])
    assert ResultCache(persistent_key="version").get_or_create("key", lambda: result) == result


def test_original_generation_time_controls_disk_expiry():
    result = ProjectionSlateResult(projections=[], skipped=[],
                                   generated_at=datetime.now(timezone.utc) - timedelta(seconds=20))
    ResultCache(ttl_seconds=30, persistent_key="version").get_or_create("key", lambda: result)
    builder = Mock(return_value=ProjectionSlateResult(projections=[], skipped=[]))
    # A shorter TTL must reject an entry even if its SQLite expiry is later.
    ResultCache(ttl_seconds=10, persistent_key="version").get_or_create("key", builder)
    builder.assert_called_once()


def test_espn_projection_survives_restart():
    from app.integrations.espn_roster_projection import ESPNRosterProjection

    player = ESPNRosterProjection(501, "id", "Player", "RB", "RB", "BUF", "MIA", 20.0, "projected")
    result = ESPNLeagueWeekProjection(datetime.now(timezone.utc), 1, {1: (player,)})
    key = (123, 2024, 1, "roster:data:model")
    assert ESPNProjectionCache(persistent=True).get_or_create(key, lambda: result) == (result, False)
    builder = Mock(side_effect=AssertionError("must use disk"))
    restored, hit = ESPNProjectionCache(persistent=True).get_or_create(key, builder)
    assert restored == result and hit
    builder.assert_not_called()


def test_cached_league_is_not_blocked_by_another_generation_building():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    cache = ESPNProjectionCache()
    result = ESPNLeagueWeekProjection(datetime.now(timezone.utc), 1, {})
    old_key, fresh_key = (123, 2024, 1, "old"), (123, 2024, 1, "fresh")
    cache.get_or_create(old_key, lambda: result)
    started, release = Event(), Event()
    def build():
        started.set()
        assert release.wait(timeout=3)
        return result
    with ThreadPoolExecutor(max_workers=2) as executor:
        updating = executor.submit(cache.get_or_create, fresh_key, build)
        try:
            assert started.wait(timeout=3)
            cached = executor.submit(cache.get_or_create, old_key, lambda: None)
            assert cached.result(timeout=1) == (result, True)
        finally:
            release.set()
        assert updating.result(timeout=3) == (result, False)


def test_espn_fallback_input_change_invalidates_fingerprint():
    from types import SimpleNamespace
    from app.services.espn_projection_cache import roster_fingerprint

    player = SimpleNamespace(playerId=501, name="Player", position="RB", lineupSlot="RB",
                             stats={1: {"projected_points": 12}})
    league = SimpleNamespace(teams=[SimpleNamespace(team_id=1, roster=[player])])
    before = roster_fingerprint(league, week=1)
    player.stats[1]["projected_points"] = 15
    assert roster_fingerprint(league, week=1) != before


@pytest.fixture
def snapshot_service(monkeypatch):
    calls = []
    def load(service, season):
        calls.append(season)
        for name in service._SNAPSHOT_FIELDS:
            setattr(service.data, name, pd.DataFrame({"id": ["a"], "week": [1]}))
        service.player_df = pd.DataFrame({"player_id": ["a"], "season": [season]})
        service.defense_df = pd.DataFrame({"team": ["BUF"]})
    monkeypatch.setattr(weekly, "source_fingerprint", lambda: "source-v1")
    monkeypatch.setattr(weekly, "model_fingerprint", lambda: "model-v1")
    monkeypatch.setattr(weekly.WeeklyProjectionService, "_load_data", load)
    return calls


def test_snapshot_skips_downloads_and_preparation_after_restart(snapshot_service, monkeypatch):
    first = weekly.WeeklyProjectionService(2024)
    restored = weekly.WeeklyProjectionService(2024)
    assert restored.generation == first.generation
    assert snapshot_service == [2024]
    pd.testing.assert_frame_equal(restored.player_df, first.player_df)
    monkeypatch.setattr(weekly, "model_fingerprint", lambda: "model-v2")
    changed_model = weekly.WeeklyProjectionService(2024)
    assert changed_model.generation != restored.generation
    assert snapshot_service == [2024]
    refreshed = weekly.WeeklyProjectionService(2024, refresh=True)
    assert refreshed.generation != changed_model.generation
    assert snapshot_service == [2024, 2024]
    assert weekly.WeeklyProjectionService(2024).generation == refreshed.generation


def test_cached_projection_needs_no_dataframe_decoding(snapshot_service, monkeypatch):
    from app.services import data_snapshot

    first = weekly.WeeklyProjectionService(2024)
    result = ProjectionSlateResult(projections=[], skipped=[])
    monkeypatch.setattr(first, "_project_week_uncached", lambda *args: result)
    first.project_week(1, "QB")
    reader = Mock(wraps=data_snapshot.pd.read_parquet)
    monkeypatch.setattr(data_snapshot.pd, "read_parquet", reader)
    restored = weekly.WeeklyProjectionService(2024)
    assert restored.project_week(1, "QB") == result
    reader.assert_not_called()
    assert len(restored.data.schedule) == 1
    assert len(restored.data.schedule) == 1
    assert reader.call_count == 1
    assert len(restored.player_df) == 1
    assert reader.call_count == 2


def test_expired_or_changed_source_reloads_snapshot(snapshot_service, monkeypatch):
    weekly.WeeklyProjectionService(2024)
    monkeypatch.setattr(weekly, "source_fingerprint", lambda: "source-v2")
    weekly.WeeklyProjectionService(2024)
    assert snapshot_service == [2024, 2024]
    original_time = disk_module.time()
    monkeypatch.setattr(disk_module, "time", lambda: original_time + 6 * 3600 + 1)
    weekly.WeeklyProjectionService(2024)
    assert snapshot_service == [2024, 2024, 2024]


def test_special_teams_snapshot_avoids_play_by_play_download(snapshot_service, monkeypatch):
    frames = {"K": pd.DataFrame({"points": [3]}), "DST": pd.DataFrame({"points": [6]})}
    loader = Mock(return_value=frames)
    monkeypatch.setattr(weekly, "load_special_teams_weekly", loader)
    weekly.WeeklyProjectionService(2024)._load_special_teams_data()
    restored = weekly.WeeklyProjectionService(2024)._load_special_teams_data()
    pd.testing.assert_frame_equal(restored["K"], frames["K"])
    loader.assert_called_once()
