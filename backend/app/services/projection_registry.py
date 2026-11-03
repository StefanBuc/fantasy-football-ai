from collections import OrderedDict
from threading import Lock

from app.services.weekly_projection_service import WeeklyProjectionService


class ProjectionServiceRegistry:
    """Share season data across routes and replace it only after a successful reload."""

    def __init__(self, max_entries: int = 2):
        self._services: OrderedDict[int, WeeklyProjectionService] = OrderedDict()
        self._lock = Lock()
        self._build_locks: dict[int, Lock] = {}
        self.max_entries = max_entries

    def get(self, season: int, refresh: bool = False) -> WeeklyProjectionService:
        with self._lock:
            previous = self._services.get(season)
            if previous is not None and not refresh:
                self._services.move_to_end(season)
                return previous
            build_lock = self._build_locks.setdefault(season, Lock())

        # Leave the previous service usable while network/decoding work runs.
        with build_lock:
            with self._lock:
                current = self._services.get(season)
                if current is not None and (not refresh or current is not previous):
                    self._services.move_to_end(season)
                    return current
            replacement = (
                WeeklyProjectionService(season=season, refresh=True)
                if refresh else WeeklyProjectionService(season=season)
            )
            with self._lock:
                self._services[season] = replacement
                self._services.move_to_end(season)
                while len(self._services) > self.max_entries:
                    self._services.popitem(last=False)
            return replacement


projection_services = ProjectionServiceRegistry()
