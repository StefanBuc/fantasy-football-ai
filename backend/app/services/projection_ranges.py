"""Historical residual ranges, bound to the exact calibrated checkpoint files."""

from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np

RANGE_PATH = Path(__file__).resolve().parents[1] / "config" / "projection_ranges.json"


def checkpoint_hashes():
    from app.config.model_config import SELECTED_PYTORCH_MODEL_VERSIONS
    root = Path(__file__).resolve().parents[2] / "models" / "pytorch"
    return {position: sha256(path.read_bytes()).hexdigest()
            for position, version in SELECTED_PYTORCH_MODEL_VERSIONS.items()
            if (path := root / f"{position}_model_v{version}.pth").is_file()}


def fit_residual_range(calibration, validation, minimum_calibration=100, minimum_validation=50):
    """Fit on earlier games only; validation outcomes never choose the bounds."""
    calibration = np.asarray(calibration, dtype=float)
    validation = np.asarray(validation, dtype=float)
    calibration = calibration[np.isfinite(calibration)]
    validation = validation[np.isfinite(validation)]
    if len(calibration) < minimum_calibration or len(validation) < minimum_validation:
        return {"ready": False, "calibration_count": len(calibration), "validation_count": len(validation)}
    low, high = np.quantile(calibration, [0.1, 0.9])
    low, high = min(float(low), 0.0), max(float(high), 0.0)
    return {"ready": True, "low_offset": low, "high_offset": high,
            "calibration_count": len(calibration), "validation_count": len(validation),
            "validation_coverage": float(np.mean((validation >= low) & (validation <= high))),
            "target_coverage": 0.8}


@lru_cache(maxsize=4)
def _read_ranges(path, modified, size):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format_version") != 1:
        raise ValueError("Unsupported projection range format")
    return data


def estimate_range(points, position, method, model_hashes):
    empty = {"floor_points": None, "ceiling_points": None,
             "range_note": "Range unavailable: no validated calibration for this projection.",
             "range_revision": None}
    if points is None or not math.isfinite(points):
        return empty
    position = position.replace("D/ST", "DST")
    try:
        stat = RANGE_PATH.stat()
        artifact = _read_ranges(str(RANGE_PATH), stat.st_mtime_ns, stat.st_size)
        entry = artifact["positions"][position]
        fitted = entry["methods"][method]
        if not fitted["ready"] or entry["checkpoint_sha256"] != model_hashes.get(position):
            return empty
        low, high = float(fitted["low_offset"]), float(fitted["high_offset"])
        if not all(math.isfinite(value) for value in (low, high)) or not low <= 0 <= high:
            return empty
        return {"floor_points": points + low, "ceiling_points": points + high,
                "range_revision": entry["checkpoint_sha256"],
                "range_note": (f"Estimated low/high outcomes from {artifact['season']} residuals; "
                    f"80% target range, {fitted['validation_coverage']:.0%} coverage on "
                    f"{fitted['validation_count']} later validation games. Outcomes can fall outside this range. "
                    "AI scoring: full PPR offense and app K/DST rules.")}
    except (OSError, ValueError, KeyError, TypeError):
        return empty
