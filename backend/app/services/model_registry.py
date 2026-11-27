"""Immutable trained artifacts and an atomically replaced active-model manifest."""

from hashlib import sha256
from functools import lru_cache
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

from filelock import FileLock

from app.config.model_config import SELECTED_PYTORCH_MODEL_VERSIONS

BASE_MODELS = Path(__file__).resolve().parents[2] / "models/pytorch"


def runs_directory():
    data = Path(os.getenv("FANTASY_HISTORY_PATH", str(Path(__file__).resolve().parents[2] / "data/predictions.sqlite3"))).parent
    return Path(os.getenv("FANTASY_MODEL_RUNS_PATH", str(data / "retraining")))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


@lru_cache(maxsize=8)
def _read_manifest(path, modified, size):
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("format_version") != 1 or not isinstance(value.get("positions"), dict):
        raise ValueError("Invalid active model manifest")
    return value


def manifest():
    path = runs_directory() / "active.json"
    if not path.exists():
        return {"format_version": 1, "positions": {}}
    stat = path.stat()
    return _read_manifest(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=64)
def _artifact_digest(path, modified, size):
    return sha256(Path(path).read_bytes()).hexdigest()


def artifact_path(relative):
    root = runs_directory().resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Model artifact is outside the training directory")
    return path


def active_artifacts(position):
    entry = manifest()["positions"].get(position)
    if entry is None:
        return None
    for name in ("checkpoint", "ranges"):
        path = artifact_path(entry[name])
        stat = path.stat()
        if _artifact_digest(str(path), stat.st_mtime_ns, stat.st_size) != entry[name + "_sha256"]:
            raise ValueError("Active model artifact checksum differs from its manifest")
    return entry


def selected_model_path(position, base_directory=None):
    position = position.upper()
    version = SELECTED_PYTORCH_MODEL_VERSIONS[position]
    entry = active_artifacts(position)
    if entry:
        return artifact_path(entry["checkpoint"])
    return Path(base_directory or BASE_MODELS) / f"{position}_model_v{version}.pth"


def active_revision():
    # Cheap cross-process invalidation. Artifacts themselves are immutable.
    path = runs_directory() / "active.json"
    return sha256(path.read_bytes()).hexdigest() if path.exists() else "bundled"


def promote(position, checkpoint, ranges, *, expected_incumbent, report):
    root = runs_directory()
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / "promotion.lock"), timeout=5):
        current = selected_model_path(position)
        if sha256(current.read_bytes()).hexdigest() != expected_incumbent:
            raise ValueError("Live model changed during evaluation; candidate must be evaluated again")
        candidate, range_path = Path(checkpoint).resolve(), Path(ranges).resolve()
        relative = [str(path.relative_to(root.resolve())).replace("\\", "/") for path in (candidate, range_path)]
        value = deepcopy(manifest())
        previous = value["positions"].get(position)
        value["positions"][position] = {
            "checkpoint": relative[0], "ranges": relative[1],
            "checkpoint_sha256": sha256(candidate.read_bytes()).hexdigest(),
            "ranges_sha256": sha256(range_path.read_bytes()).hexdigest(),
            "previous": previous, "evaluation": report,
        }
        atomic_json(root / "active.json", value)


def rollback(position):
    root = runs_directory()
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / "promotion.lock"), timeout=5):
        value = deepcopy(manifest())
        entry = value["positions"].get(position)
        if entry:
            previous = entry.get("previous")
            if previous:
                value["positions"][position] = previous
            else:
                value["positions"].pop(position)
            atomic_json(root / "active.json", value)
