import torch
import pytest


@pytest.fixture(autouse=True)
def isolated_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("FANTASY_AUTH_ENABLED", "false")
    monkeypatch.setenv("FANTASY_ACCOUNT_PATH", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("FANTASY_ENCRYPTION_KEY_PATH", str(tmp_path / "secrets" / "credentials.key"))
    monkeypatch.setenv("FANTASY_AUTOMATION_ENABLED", "false")
    from app.services.disk_cache import disk_cache

    monkeypatch.setattr(disk_cache, "path", tmp_path / "runtime.sqlite3")
    from app.services.prediction_history import prediction_history

    monkeypatch.setattr(prediction_history, "path", tmp_path / "predictions.sqlite3")
