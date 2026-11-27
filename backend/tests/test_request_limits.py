import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from main import app
from app.services import request_limits as module
from app.services.request_limits import RequestLimits, expensive, call_limited
from app.routes import espn
from test_accounts import secured, login


def test_slots_are_shared_between_instances_and_return_after_release(tmp_path, monkeypatch):
    monkeypatch.setenv("FANTASY_MAX_EXPENSIVE_REQUESTS", "1")
    first, other = RequestLimits(tmp_path), RequestLimits(tmp_path)
    lease, _, _ = first.acquire()
    assert lease is not None
    assert other.acquire()[0] is None
    lease.release()
    lease, _, _ = other.acquire()
    assert lease is not None
    lease.release()


def test_process_exit_releases_slot_without_waiting_for_a_lease_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("FANTASY_MAX_EXPENSIVE_REQUESTS", "1")
    code = ("import sys; from app.services.request_limits import RequestLimits; "
            "lock,_,_=RequestLimits(sys.argv[1]).acquire(); assert lock is not None; "
            "print('ready',flush=True); sys.stdin.read()")
    with subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as child:
        try:
            assert child.stdout.readline().strip() == "ready"
            assert RequestLimits(tmp_path).acquire()[0] is None
        finally:
            child.kill()
            child.wait(timeout=5)
    lease, _, _ = RequestLimits(tmp_path).acquire()
    assert lease is not None
    lease.release()


def test_rate_and_refresh_windows_persist_across_instances(tmp_path, monkeypatch):
    now = [1000.]
    monkeypatch.setenv("FANTASY_EXPENSIVE_REQUESTS_PER_MINUTE", "3")
    cache = RequestLimits(tmp_path, clock=lambda: now[0])
    for _ in range(2):
        lease, _, _ = cache.acquire(refresh=True)
        lease.release()
    lease, wait, detail = RequestLimits(tmp_path, clock=lambda: now[0]).acquire(refresh=True)
    assert lease is None and wait == 300 and "refreshes" in detail
    lease, _, _ = cache.acquire()
    lease.release()
    assert cache.acquire()[1] == 60
    now[0] += 61
    lease, _, _ = cache.acquire()
    lease.release()
    assert cache.acquire(refresh=True)[1] == 239
    now[0] += 240
    lease, _, _ = cache.acquire(refresh=True)
    assert lease is not None
    lease.release()


@pytest.mark.parametrize("method,path", [("GET", "/api/health/"), ("GET", "/api/accuracy/2026"),
    ("GET", "/api/training/status"), ("POST", "/api/espn/local/live"), ("PATCH", "/api/account/preferences")])
def test_lightweight_routes_do_not_take_expensive_slots(method, path):
    assert not expensive(method, path)


def test_limited_response_has_retry_header_and_does_not_block_history_or_health(monkeypatch):
    monkeypatch.setenv("FANTASY_REQUEST_LIMITS_ENABLED", "true")
    monkeypatch.setenv("FANTASY_EXPENSIVE_REQUESTS_PER_MINUTE", "1")
    client = TestClient(app)
    assert client.get("/api/metadata/").status_code == 200
    blocked = client.get("/api/metadata/", headers={"X-Forwarded-For": "different-client", "CF-Connecting-IP": "different-client"})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert client.get("/api/health/").status_code == 200
    assert client.get("/api/accuracy/2026").status_code == 200


def test_post_body_reaches_route_and_truthy_refresh_cannot_bypass_limit(monkeypatch):
    monkeypatch.setenv("FANTASY_REQUEST_LIMITS_ENABLED", "true")
    from app.schemas.espn import ESPNTeamProjectionResponse
    response = ESPNTeamProjectionResponse(league_id=123, league_name="League", season=2026, week=12,
        roster_week=12, team_id=1, team_name="Team", generated_at="2026-11-27T12:00:00Z", cache_hit=True,
        projected_count=0, skipped_count=0, players=[])
    builder = Mock(return_value=response)
    monkeypatch.setattr(espn, "get_public_league", Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(espn.projection_services, "get", Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(espn, "build_team_projection_response", builder)
    client = TestClient(app)
    payload = {"league_id": 123, "season": 2026, "week": 12, "team_id": 1}
    for refresh in (True, "YES"):
        assert client.post("/api/espn/projections", json={**payload, "refresh": refresh}).status_code == 200
    assert builder.call_count == 2 and builder.call_args.kwargs["team_id"] == 1
    assert client.post("/api/espn/projections", json={**payload, "refresh": "on"}).status_code == 429
    assert client.post("/api/espn/projections", json=payload).status_code == 200


def test_authentication_happens_before_limits_and_sessions_share_owner_budget(secured, monkeypatch):
    monkeypatch.setenv("FANTASY_REQUEST_LIMITS_ENABLED", "true")
    monkeypatch.setenv("FANTASY_EXPENSIVE_REQUESTS_PER_MINUTE", "1")
    assert secured.get("/api/metadata/").status_code == 401
    login(secured)
    assert secured.get("/api/metadata/").status_code == 200
    # A new owner session cannot reset the application-wide budget.
    second = TestClient(app, base_url="https://ffa.stefanb.me")
    login(second)
    assert second.get("/api/metadata/").status_code == 429
    assert second.get("/api/training/status").status_code == 200


def test_failure_and_cancellation_release_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("FANTASY_REQUEST_LIMITS_ENABLED", "true")
    monkeypatch.setenv("FANTASY_MAX_EXPENSIVE_REQUESTS", "1")
    limiter = RequestLimits(tmp_path)
    monkeypatch.setattr(module, "request_limits", limiter)
    def request():
        return Request({"type": "http", "method": "GET", "path": "/api/metadata/", "query_string": b"", "headers": []})
    async def scenario():
        async def fail(_):
            raise ValueError("Broken route")
        with pytest.raises(ValueError):
            await call_limited(request(), fail)
        started = asyncio.Event()
        async def wait(_):
            started.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(call_limited(request(), wait))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        lease, _, _ = limiter.acquire()
        assert lease is not None
        lease.release()
    asyncio.run(scenario())
