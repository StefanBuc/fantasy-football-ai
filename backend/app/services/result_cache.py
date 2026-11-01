from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import Callable, Generic, Hashable, TypeVar
from app.services.performance import logger


T = TypeVar("T")


class ResultCache(Generic[T]):
    """Bounded process-local TTL cache; concurrent misses share one build."""

    def __init__(self, ttl_seconds: float = 900, max_entries: int = 128,
                 name: str = "results"):
        if ttl_seconds <= 0 or max_entries < 1:
            raise ValueError("Cache TTL and capacity must be positive.")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.name = name
        self._entries: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()
        self._lock = Lock()

    def get_or_create(self, key: Hashable, builder: Callable[[], T]) -> T:
        started = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and monotonic() < entry[0]:
                self._entries.move_to_end(key)
                logger.info(
                    "cache=%s result=hit key=%s duration_ms=%.2f",
                    self.name, key, (monotonic() - started) * 1000,
                )
                return deepcopy(entry[1])

            # Failed builds are never cached. Start the TTL after computation.
            self._entries.pop(key, None)
            logger.info("cache=%s result=miss key=%s", self.name, key)
            result = builder()
            self._entries[key] = (
                monotonic() + self.ttl_seconds,
                deepcopy(result),
            )
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            logger.info(
                "cache=%s result=stored key=%s duration_ms=%.2f",
                self.name, key, (monotonic() - started) * 1000,
            )
            return result

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
