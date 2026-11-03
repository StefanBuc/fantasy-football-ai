from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile
from threading import RLock

import pandas as pd

from app.config.model_config import SELECTED_PYTORCH_MODEL_VERSIONS
from app.services.performance import timed_stage


def source_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = sha256(b"snapshot-v1")
    # Invalidate for feature/projection changes, not logging or cache plumbing.
    source_files = (
        "services/NFL_data.py", "services/defense_features.py",
        "services/player_sequence_dataset.py", "services/special_teams_data.py",
        "services/special_teams_sequence_dataset.py", "services/teammate_injury_features.py",
        "services/projection_slate.py", "services/projection_types.py",
        "services/pytorch_inference.py", "services/pytorch_projection_model.py",
        "services/special_teams_inference.py", "config/model_config.py",
        "integrations/espn_roster_projection.py", "integrations/espn_player_matching.py",
    )
    for path in sorted(root / name for name in source_files):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
        digest.update(path.read_bytes())
    for package in ("pandas", "numpy", "fastparquet"):
        digest.update(version(package).encode())
    return digest.hexdigest()


def model_fingerprint() -> str:
    root = Path(__file__).resolve().parents[2] / "models" / "pytorch"
    digest = sha256()
    for position, model_version in sorted(SELECTED_PYTORCH_MODEL_VERSIONS.items()):
        path = root / f"{position}_model_v{model_version}.pth"
        digest.update(path.name.encode())
        digest.update(path.read_bytes() if path.exists() else b"missing")
    return digest.hexdigest()


def encode_frames(frames: dict[str, pd.DataFrame], metadata: dict) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("metadata.json", json.dumps(metadata))
        for name, frame in frames.items():
            buffer = BytesIO()
            # ID imports can mix strings, numbers, and nulls in object columns.
            # JSON column encoding preserves those values instead of guessing a type.
            frame.to_parquet(buffer, engine="fastparquet", index=False,
                             object_encoding={column: "json" for column in
                                              frame.select_dtypes(include="object").columns})
            archive.writestr(f"{name}.parquet", buffer.getvalue())
    return output.getvalue()


def decode_frames(payload: bytes) -> tuple[dict[str, pd.DataFrame], dict]:
    with ZipFile(BytesIO(payload)) as archive:
        metadata = json.loads(archive.read("metadata.json"))
        frames = {
            name.removesuffix(".parquet"): pd.read_parquet(
                BytesIO(archive.read(name)), engine="fastparquet",
            )
            for name in archive.namelist() if name.endswith(".parquet")
        }
    return frames, metadata


class FrameSnapshot:
    """Inspect the archive immediately; decode each table only on first use."""

    def __init__(self, payload: bytes):
        self._payload = payload
        self._frames: dict[str, pd.DataFrame] = {}
        self._lock = RLock()
        with ZipFile(BytesIO(payload)) as archive:
            self.metadata = json.loads(archive.read("metadata.json"))
            self.names = frozenset(name.removesuffix(".parquet")
                                   for name in archive.namelist() if name.endswith(".parquet"))

    def __getitem__(self, name: str) -> pd.DataFrame:
        if name not in self.names:
            raise KeyError(name)
        with self._lock:
            if name not in self._frames:
                with timed_stage("restore_nfl_table", table=name):
                    with ZipFile(BytesIO(self._payload)) as archive:
                        self._frames[name] = pd.read_parquet(
                            BytesIO(archive.read(f"{name}.parquet")), engine="fastparquet",
                        )
            return self._frames[name]
