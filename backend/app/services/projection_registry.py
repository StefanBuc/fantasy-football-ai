from collections import OrderedDict
from threading import Lock

from app.services.weekly_projection_service import WeeklyProjectionService


class ProjectionServiceRegistry:
    """Share season data across routes and replace it only after a successful reload."""

    def __init__(self, max_entries: int = 2):
        self._services: OrderedDict[int, WeeklyProjectionService] = OrderedDict()
        self._lock = Lock()
        self.max_entries = max_entries

    def get(self, season: int, refresh: bool = False) -> WeeklyProjectionService:
        with self._lock:
            if refresh or season not in self._services:
                # Construction reloads NFL data and drops prepared models/results.
                # Keep the previous service available if construction fails.
                replacement = WeeklyProjectionService(season=season)
                self._services[season] = replacement
            self._services.move_to_end(season)
            while len(self._services) > self.max_entries:
                self._services.popitem(last=False)
            return self._services[season]


projection_services = ProjectionServiceRegistry()
