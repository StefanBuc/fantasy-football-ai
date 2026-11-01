import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.performance import timed_stage
from app.services.result_cache import ResultCache
from main import app


def test_stage_records_elapsed_time_and_failures(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error.performance"):
        with patch("app.services.performance.perf_counter", side_effect=[1, 1.25]):
            with pytest.raises(ValueError, match="broken"):
                with timed_stage("features", season=2024):
                    raise ValueError("broken")
    assert "stage=features outcome=error duration_ms=250.00" in caplog.text


def test_cache_logs_hit_and_miss(caplog):
    cache = ResultCache(name="weekly")
    with caplog.at_level(logging.INFO, logger="uvicorn.error.performance"):
        assert cache.get_or_create((2024, 1, "QB"), lambda: 20) == 20
        assert cache.get_or_create((2024, 1, "QB"), lambda: 99) == 20
    assert "cache=weekly result=miss" in caplog.text
    assert "cache=weekly result=hit" in caplog.text


def test_request_timing_header_and_private_query_omitted(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error.performance"):
        response = TestClient(app).get(
            "/missing?token=private-test-value", headers={"Origin": "http://localhost:5173"}
        )
    assert response.status_code == 404
    assert float(response.headers["X-Response-Time-ms"]) >= 0
    assert "x-response-time-ms" in response.headers["access-control-expose-headers"].lower()
    assert "status=404" in caplog.text
    assert "private-test-value" not in caplog.text
