from unittest.mock import Mock

import pytest

from app.services import espn_connection_cache as module
from app.services.espn_connection_cache import ESPNConnectionCache


def test_connect_and_projection_share_league_until_expiry(monkeypatch):
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(module, "monotonic", clock)
    cache = ESPNConnectionCache(ttl_seconds=15)
    first, second = object(), object()
    builder = Mock(side_effect=[first, second])
    assert cache.get(123, 2026, None, None, builder) is first
    assert cache.get(123, 2026, None, None, builder) is first
    assert builder.call_count == 1
    clock.return_value = 115.0
    assert cache.get(123, 2026, None, None, builder) is second


def test_credentials_and_leagues_are_isolated_and_refresh_clears():
    cache = ESPNConnectionCache()
    builder = Mock(side_effect=lambda: object())
    first = cache.get(123, 2026, "cookie-a", "id", builder)
    assert cache.get(123, 2026, "cookie-b", "id", builder) is not first
    assert cache.get(124, 2026, "cookie-a", "id", builder) is not first
    assert cache.get(123, 2026, "cookie-a", "id", builder) is first
    cache.clear()
    assert cache.get(123, 2026, "cookie-a", "id", builder) is not first


def test_failed_league_download_is_not_cached():
    cache = ESPNConnectionCache()
    builder = Mock(side_effect=[RuntimeError("failed"), object()])
    with pytest.raises(RuntimeError, match="failed"):
        cache.get(123, 2026, None, None, builder)
    assert cache.get(123, 2026, None, None, builder) is not None
    assert builder.call_count == 2
