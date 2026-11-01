from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from unittest import TestCase
from unittest.mock import patch

from app.services import result_cache
from app.services.result_cache import ResultCache


def test_hits_expiry_and_mutation_isolation():
    clock = Mock(return_value=100.0)
    builder = Mock(side_effect=lambda: [1])
    cache = ResultCache(ttl_seconds=10)

    with patch.object(result_cache, "monotonic", clock):
        cache.get_or_create("QB", builder).append(2)
        assert cache.get_or_create("QB", builder) == [1]
        assert builder.call_count == 1
        clock.return_value = 110.0
        assert cache.get_or_create("QB", builder) == [1]
        assert builder.call_count == 2


def test_lru_eviction_and_clear():
    cache = ResultCache(max_entries=2)
    builder = Mock(return_value=1)
    for key in ("QB", "RB", "QB", "WR", "RB"):
        cache.get_or_create(key, builder)
    assert builder.call_count == 4
    cache.clear()
    cache.get_or_create("RB", builder)
    assert builder.call_count == 5


def test_failed_build_can_be_retried():
    cache = ResultCache()
    builder = Mock(side_effect=[ValueError("failed"), 2])
    with TestCase().assertRaisesRegex(ValueError, "failed"):
        cache.get_or_create("QB", builder)
    assert cache.get_or_create("QB", builder) == 2


def test_concurrent_requests_build_once():
    cache = ResultCache()
    builder = Mock(return_value=[1])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: cache.get_or_create("QB", builder), range(16)
        ))
    assert results == [[1]] * 16
    builder.assert_called_once()


def test_weekly_service_keys_by_week_and_position():
    from app.services.weekly_projection_service import WeeklyProjectionService

    service = object.__new__(WeeklyProjectionService)
    service.season = 2024
    service.weekly_cache = ResultCache()
    service._project_week_uncached = Mock(return_value="projection")
    for week, position in ((1, "qb"), (1, "QB"), (2, "QB"), (1, "RB")):
        assert service.project_week(week, position) == "projection"
    assert service._project_week_uncached.call_count == 3
    with TestCase().assertRaises(ValueError):
        service.project_week(0, "QB")


if __name__ == "__main__":
    from unittest import FunctionTestCase, TextTestRunner, TestSuite

    suite = TestSuite(
        FunctionTestCase(test)
        for name, test in list(globals().items())
        if name.startswith("test_")
    )
    raise SystemExit(not TextTestRunner(verbosity=2).run(suite).wasSuccessful())
