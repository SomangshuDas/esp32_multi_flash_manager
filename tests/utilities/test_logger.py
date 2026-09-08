"""
Tests for app/logging_setup/logger.py: the four always-on rotating text
logs, and the optional fifth structured JSON log (events.jsonl) gated by
Settings -> Diagnostics -> "Enable structured JSON logging".
"""

from __future__ import annotations

import json
import logging

import pytest

import app.logging_setup.logger as logger_module
import app.utilities.app_settings as app_settings_module
from app.utilities.constants import JSON_LOG_FILENAME, SETTINGS_KEY_JSON_LOGGING_ENABLED


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Point both the app-data dir and AppSettings at a throwaway
    directory, and always reset logger_module._CONFIGURED plus the root
    logger's handlers so each test gets a fresh configure_logging() call
    instead of the process-wide singleton short-circuiting it."""
    monkeypatch.setattr(logger_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_settings_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_settings_module, "_instance", None)
    monkeypatch.setattr(logger_module, "_CONFIGURED", False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    for h in original_handlers:
        root.removeHandler(h)
    yield tmp_path
    for h in list(root.handlers):
        root.removeHandler(h)
        with pytest.MonkeyPatch.context():
            pass
    for h in original_handlers:
        root.addHandler(h)
    monkeypatch.setattr(app_settings_module, "_instance", None)


class TestConfigureLogging:
    def test_creates_four_text_logs(self, tmp_path):
        log_dir = logger_module.configure_logging()
        logging.getLogger("app.test").info("hello")
        for name in ("application.log", "flash.log", "error.log", "debug.log"):
            assert (log_dir / name).exists()

    def test_json_log_absent_by_default(self, tmp_path):
        log_dir = logger_module.configure_logging()
        assert not (log_dir / JSON_LOG_FILENAME).exists()

    def test_json_log_created_when_enabled(self, tmp_path):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_JSON_LOGGING_ENABLED, True)
        log_dir = logger_module.configure_logging()
        test_logger = logging.getLogger("app.test.json")
        test_logger.info("a structured event")
        json_path = log_dir / JSON_LOG_FILENAME
        assert json_path.exists()
        lines = [ln for ln in json_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert lines, "expected at least one JSON line to be written"
        record = json.loads(lines[-1])
        assert record["message"] == "a structured event"
        assert record["logger"] == "app.test.json"
        assert record["level"] == "INFO"

    def test_second_call_is_a_no_op(self, tmp_path):
        first = logger_module.configure_logging()
        root_handler_count = len(logging.getLogger().handlers)
        second = logger_module.configure_logging()
        assert first == second
        assert len(logging.getLogger().handlers) == root_handler_count
