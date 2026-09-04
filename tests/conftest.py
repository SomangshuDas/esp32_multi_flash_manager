"""
Shared pytest fixtures for the whole test suite.

Key responsibilities:
  - Force Qt into headless (offscreen) mode before anything imports
    PySide6, so the entire suite runs on CI / any machine with no display.
  - Isolate every test's "app data directory" (settings.json, firmware
    profiles, history, ...) to a fresh temporary folder instead of the
    real per-user location, so tests never read/write a developer's or
    CI runner's actual ESP32MultiFlashManager app-data folder and never
    leak state between tests.
  - Reset the AppSettings process-wide singleton between tests, since it
    is otherwise cached at module scope (see app/utilities/app_settings.py).
"""

from __future__ import annotations

import os
import sys

# Must happen before any PySide6 import anywhere in the process.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_app_data_dir(tmp_path, monkeypatch):
    """Point get_app_data_dir() at a fresh temp folder for every test."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data_home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "platform", sys.platform)  # keep real OS branch

    import app.utilities.app_settings as app_settings_module

    monkeypatch.setattr(app_settings_module, "_instance", None)
    yield
    monkeypatch.setattr(app_settings_module, "_instance", None)


@pytest.fixture
def qapp_instance(qapp):
    """Thin alias fixture name some tests use; pytest-qt already provides `qapp`."""
    return qapp


@pytest.fixture
def make_firmware_file(tmp_path):
    """Factory fixture: write a firmware .bin file with given content/name."""

    def _make(name: str = "firmware.bin", content: bytes = b"\x00" * 256, directory=None) -> str:
        directory = directory or tmp_path
        path = directory / name
        path.write_bytes(content)
        return str(path)

    return _make
