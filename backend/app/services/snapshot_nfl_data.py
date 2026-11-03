from app.services.NFL_data import NFLData
from app.services.data_snapshot import FrameSnapshot


class SnapshotNFLData(NFLData):
    """Keep the normal NFLData methods while loading saved tables on demand."""

    def __init__(self, seasons: list[int], snapshot: FrameSnapshot, fields: tuple[str, ...]):
        super().__init__(seasons)
        self._snapshot = snapshot
        self._snapshot_fields = frozenset(fields)
        for name in fields:
            delattr(self, name)

    def __getattr__(self, name):
        if name in self._snapshot_fields:
            frame = self._snapshot[name]
            setattr(self, name, frame)
            return frame
        raise AttributeError(name)
