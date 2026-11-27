"""Process-shared limits for model/data requests; polling and history reads stay available."""

import asyncio
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from time import time

from fastapi.responses import JSONResponse
from filelock import FileLock, Timeout


def enabled():
    return os.getenv("FANTASY_REQUEST_LIMITS_ENABLED", "true").lower() in {"true", "1", "yes"}


def positive_setting(name, default, maximum):
    return max(1, min(maximum, int(os.getenv(name, str(default)))))


def limits_directory():
    cache = Path(os.getenv("FANTASY_CACHE_PATH", str(Path(__file__).resolve().parents[2] / "cache/runtime.sqlite3")))
    return cache.parent / "request-limits"


def expensive(method, path):
    path = path.rstrip("/")
    if path.startswith(("/api/predictions/", "/api/players", "/api/metadata", "/api/weeks")):
        return method == "GET"
    if method not in {"POST", "PUT"}:
        return False
    return bool(re.fullmatch(
        r"/api/espn/(?:local/)?(?:connect|players|projections|matchup|optimized-lineup|trade-analysis|trade-rosters)"
        r"|/api/accuracy/\d+/sync|/api/account/(?:import-configured-league|connections(?:/[^/]+(?:/connect)?)?)", path))


class RequestLimits:
    def __init__(self, directory=None, clock=time):
        self.directory = directory
        self.clock = clock

    def root(self):
        return Path(self.directory) if self.directory is not None else limits_directory()

    def acquire(self, *, refresh=False):
        root = self.root()
        root.mkdir(parents=True, exist_ok=True)
        lock = None
        for slot in range(positive_setting("FANTASY_MAX_EXPENSIVE_REQUESTS", 2, 32)):
            candidate = FileLock(str(root / f"slot-{slot}.request.lock"), timeout=0, thread_local=False)
            try:
                candidate.acquire()
                lock = candidate
                break
            except Timeout:
                continue
        if lock is None:
            return None, 2, "The server is busy preparing projections. Try again shortly."
        try:
            now = self.clock()
            rules = [("expensive", 60, positive_setting("FANTASY_EXPENSIVE_REQUESTS_PER_MINUTE", 60, 1000))]
            if refresh:
                rules.append(("refresh", 300, positive_setting("FANTASY_REFRESH_REQUESTS_PER_FIVE_MINUTES", 2, 100)))
            with sqlite3.connect(root / "requests.sqlite3", timeout=2) as db:
                db.execute("CREATE TABLE IF NOT EXISTS events (bucket TEXT NOT NULL, happened REAL NOT NULL)")
                db.execute("CREATE INDEX IF NOT EXISTS events_by_bucket ON events(bucket,happened)")
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM events WHERE happened<=? OR happened>?", (now - 300, now))
                for bucket, window, maximum in rules:
                    count, oldest = db.execute("SELECT COUNT(*),MIN(happened) FROM events WHERE bucket=? AND happened>?",
                                               (bucket, now - window)).fetchone()
                    if count >= maximum:
                        wait = max(1, math.ceil(oldest + window - now))
                        lock.release()
                        return None, wait, f"Too many {'data refreshes' if bucket == 'refresh' else 'projection requests'}. Try again in {wait} seconds."
                db.executemany("INSERT INTO events VALUES (?,?)", [(bucket, now) for bucket, _, _ in rules])
            return lock, None, None
        except BaseException:
            lock.release()
            raise


request_limits = RequestLimits()


async def call_limited(request, call_next):
    if not enabled() or not expensive(request.method, request.url.path):
        return await call_next(request)
    truthy = {"1", "true", "yes", "y", "t", "on"}
    refresh = request.query_params.get("refresh", "").lower() in truthy
    if request.method in {"POST", "PUT"}:
        # ESPN request bodies are small. Cache the bounded body for the route.
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 1024 * 1024:
                return JSONResponse({"detail": "Request body is too large."}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        try:
            body = json.loads(request._body)
            if isinstance(body, dict):
                refresh = refresh or str(body.get("refresh", "")).lower() in truthy
        except (ValueError, UnicodeError):
            pass  # Let FastAPI return its normal validation error.
    pending = asyncio.create_task(asyncio.to_thread(request_limits.acquire, refresh=refresh))
    try:
        lock, wait, detail = await asyncio.shield(pending)
    except asyncio.CancelledError:
        lock, _, _ = await pending
        if lock is not None:
            await asyncio.shield(asyncio.to_thread(lock.release))
        raise
    if lock is None:
        return JSONResponse({"detail": detail}, status_code=429, headers={"Retry-After": str(wait)})
    try:
        return await call_next(request)
    finally:
        await asyncio.shield(asyncio.to_thread(lock.release))
