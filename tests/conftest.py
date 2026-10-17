"""Global test configuration and fixtures for pytest."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ensures test runs isolate settings, session, cache, and debug directories."""
    monkeypatch.setattr("mc_xbox_dl.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("mc_xbox_dl.config.SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr("mc_xbox_dl.config.SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr("mc_xbox_dl.config.DEFAULT_SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("MC_XBOX_DL_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr("mc_xbox_dl.config.CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr("mc_xbox_dl.config.DEFAULT_CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setenv("MC_XBOX_DL_CACHE_FILE", str(tmp_path / "cache.json"))
    monkeypatch.setattr("mc_xbox_dl.config.DEBUG_DIR", tmp_path / "debug")
    monkeypatch.setattr("mc_xbox_dl.cli.DOWNLOAD_INTER_WORLD_DELAY", 0.0)
    monkeypatch.setattr("mc_xbox_dl.session.SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr("mc_xbox_dl.http.DEBUG_DIR", tmp_path / "debug")
    return tmp_path
