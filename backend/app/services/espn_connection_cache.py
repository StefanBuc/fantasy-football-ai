from collections import OrderedDict
from hashlib import sha256
from threading import Lock
from time import monotonic

from app.services.performance import logger, timed_stage


class ESPNConnectionCache:
    """Briefly reuse league downloads between connection and projection requests."""

    def __init__(self, ttl_seconds: float = 15, max_entries: int = 16):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries = OrderedDict()
        self._lock = Lock()

    def get(self, league_id, year, espn_s2, swid, builder):
        credentials = sha256(repr((espn_s2, swid)).encode()).hexdigest()
        key = (int(league_id), int(year), credentials)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and monotonic() < entry[0]:
                self._entries.move_to_end(key)
                logger.info("cache=espn_connection result=hit")
                return entry[1]
            self._entries.pop(key, None)
            with timed_stage("espn_league_download"):
                league = builder()
            self._entries[key] = (monotonic() + self.ttl_seconds, league)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            return league

    def clear(self):
        with self._lock:
            self._entries.clear()


espn_connection_cache = ESPNConnectionCache()
