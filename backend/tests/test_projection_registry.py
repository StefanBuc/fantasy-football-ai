from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import projection_registry


def test_refresh_replaces_only_the_requested_season(monkeypatch):
    factory = Mock(side_effect=lambda season: SimpleNamespace(season=season))
    monkeypatch.setattr(projection_registry, "WeeklyProjectionService", factory)
    registry = projection_registry.ProjectionServiceRegistry()
    first = registry.get(2024)
    other = registry.get(2025)
    assert registry.get(2024) is first
    assert registry.get(2024, refresh=True) is not first
    assert registry.get(2025) is other
    assert factory.call_count == 3


def test_failed_reload_keeps_previous_service(monkeypatch):
    first = object()
    factory = Mock(side_effect=[first, RuntimeError("download failed")])
    monkeypatch.setattr(projection_registry, "WeeklyProjectionService", factory)
    registry = projection_registry.ProjectionServiceRegistry()
    assert registry.get(2024) is first
    with pytest.raises(RuntimeError, match="download failed"):
        registry.get(2024, refresh=True)
    assert registry.get(2024) is first


def test_concurrent_initial_load_is_shared(monkeypatch):
    factory = Mock(return_value=object())
    monkeypatch.setattr(projection_registry, "WeeklyProjectionService", factory)
    registry = projection_registry.ProjectionServiceRegistry()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: registry.get(2024), range(8)))
    assert all(result is results[0] for result in results)
    factory.assert_called_once_with(season=2024)
