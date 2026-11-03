"""Local disposable cache. Values are JSON or Parquet, never executable pickles."""

from hashlib import sha256
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from time import time

from app.services.performance import logger


class DiskCache:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=2)
        try:
            connection.execute("PRAGMA auto_vacuum = FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                "namespace TEXT, key TEXT, expires REAL, accessed REAL, payload BLOB, "
                "PRIMARY KEY(namespace, key))"
            )
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _key(key) -> str:
        return sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()

    def get(self, namespace: str, key) -> bytes | None:
        try:
            with self._connect() as connection:
                now = time()
                entry = connection.execute(
                    "SELECT expires, payload FROM entries WHERE namespace=? AND key=?",
                    (namespace, self._key(key)),
                ).fetchone()
                if entry is not None and entry[0] > now:
                    connection.execute(
                        "UPDATE entries SET accessed=? WHERE namespace=? AND key=?",
                        (now, namespace, self._key(key)),
                    )
                    logger.info("cache=%s storage=disk result=hit", namespace)
                    return bytes(entry[1])
                connection.execute("DELETE FROM entries WHERE expires<=?", (now,))
        except (OSError, sqlite3.Error) as error:
            logger.warning("Disk cache read failed; recomputing: %s", error)
        return None

    def put(self, namespace: str, key, payload: bytes, ttl_seconds: float,
            max_entries: int = 128) -> None:
        try:
            with self._connect() as connection:
                now = time()
                connection.execute("DELETE FROM entries WHERE expires<=?", (now,))
                connection.execute(
                    "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?)",
                    (namespace, self._key(key), now + ttl_seconds, now, payload),
                )
                connection.execute(
                    "DELETE FROM entries WHERE namespace=? AND key NOT IN "
                    "(SELECT key FROM entries WHERE namespace=? ORDER BY accessed DESC LIMIT ?)",
                    (namespace, namespace, max_entries),
                )
                connection.execute(
                    "DELETE FROM entries WHERE rowid NOT IN "
                    "(SELECT rowid FROM entries ORDER BY accessed DESC LIMIT 256)"
                )
        except (OSError, sqlite3.Error) as error:
            logger.warning("Disk cache write failed; using memory only: %s", error)

    def clear(self, namespace: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM entries WHERE namespace=?", (namespace,))
        except (OSError, sqlite3.Error) as error:
            logger.warning("Disk cache clear failed: %s", error)


disk_cache = DiskCache(Path(os.environ.get(
    "FANTASY_CACHE_PATH",
    str(Path(__file__).resolve().parents[2] / "cache" / "runtime.sqlite3"),
)))
