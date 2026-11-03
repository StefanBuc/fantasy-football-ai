import torch
import pytest


@pytest.fixture(autouse=True)
def isolated_disk_cache(tmp_path, monkeypatch):
    from app.services.disk_cache import disk_cache

    monkeypatch.setattr(disk_cache, "path", tmp_path / "runtime.sqlite3")
