"""
Tests for the settings getters added to app/utilities/app_settings.py as
part of the Testing/Observability/UX upgrade: get_port_scan_interval_ms(),
get_live_log_max_lines(), get_project_lock_stale_seconds(),
get_json_logging_enabled(), get_telemetry_enabled(), and
get_default_device_profile_name(). Mirrors the shape of the existing
provisioning-settings tests (test_app_settings_provisioning.py).
"""

from __future__ import annotations

import pytest

import app.utilities.app_settings as app_settings_module
from app.utilities.constants import (
    LIVE_LOG_MAX_LINES,
    LIVE_LOG_MAX_LINES_MAX,
    LIVE_LOG_MAX_LINES_MIN,
    PORT_SCAN_INTERVAL_MS,
    PORT_SCAN_INTERVAL_MS_MAX,
    PORT_SCAN_INTERVAL_MS_MIN,
    PROJECT_LOCK_STALE_SECONDS,
    PROJECT_LOCK_STALE_SECONDS_MAX,
    PROJECT_LOCK_STALE_SECONDS_MIN,
    SETTINGS_KEY_DEFAULT_DEVICE_PROFILE,
    SETTINGS_KEY_JSON_LOGGING_ENABLED,
    SETTINGS_KEY_LIVE_LOG_MAX_LINES,
    SETTINGS_KEY_PORT_SCAN_INTERVAL_MS,
    SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS,
    SETTINGS_KEY_TELEMETRY_ENABLED,
)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_settings_module, "_instance", None)
    yield
    monkeypatch.setattr(app_settings_module, "_instance", None)


class TestGetPortScanIntervalMs:
    def test_defaults_when_unset(self):
        assert app_settings_module.get_port_scan_interval_ms() == PORT_SCAN_INTERVAL_MS

    def test_respects_stored_value(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PORT_SCAN_INTERVAL_MS, 5000)
        assert app_settings_module.get_port_scan_interval_ms() == 5000

    def test_clamped_to_max(self):
        app_settings_module.get_settings().setValue(
            SETTINGS_KEY_PORT_SCAN_INTERVAL_MS, PORT_SCAN_INTERVAL_MS_MAX + 1000
        )
        assert app_settings_module.get_port_scan_interval_ms() == PORT_SCAN_INTERVAL_MS_MAX

    def test_clamped_to_min(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PORT_SCAN_INTERVAL_MS, 1)
        assert app_settings_module.get_port_scan_interval_ms() == PORT_SCAN_INTERVAL_MS_MIN

    def test_corrupted_value_falls_back_to_default(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PORT_SCAN_INTERVAL_MS, "nope")
        assert app_settings_module.get_port_scan_interval_ms() == PORT_SCAN_INTERVAL_MS


class TestGetLiveLogMaxLines:
    def test_defaults_when_unset(self):
        assert app_settings_module.get_live_log_max_lines() == LIVE_LOG_MAX_LINES

    def test_clamped_to_max(self):
        app_settings_module.get_settings().setValue(
            SETTINGS_KEY_LIVE_LOG_MAX_LINES, LIVE_LOG_MAX_LINES_MAX + 1
        )
        assert app_settings_module.get_live_log_max_lines() == LIVE_LOG_MAX_LINES_MAX

    def test_clamped_to_min(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_LIVE_LOG_MAX_LINES, 0)
        assert app_settings_module.get_live_log_max_lines() == LIVE_LOG_MAX_LINES_MIN


class TestGetProjectLockStaleSeconds:
    def test_defaults_when_unset(self):
        assert app_settings_module.get_project_lock_stale_seconds() == PROJECT_LOCK_STALE_SECONDS

    def test_clamped_to_max(self):
        app_settings_module.get_settings().setValue(
            SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS, PROJECT_LOCK_STALE_SECONDS_MAX + 100
        )
        assert app_settings_module.get_project_lock_stale_seconds() == PROJECT_LOCK_STALE_SECONDS_MAX

    def test_clamped_to_min(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS, 1)
        assert app_settings_module.get_project_lock_stale_seconds() == PROJECT_LOCK_STALE_SECONDS_MIN


class TestGetJsonLoggingEnabled:
    def test_defaults_to_false(self):
        assert app_settings_module.get_json_logging_enabled() is False

    def test_respects_stored_true(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_JSON_LOGGING_ENABLED, True)
        assert app_settings_module.get_json_logging_enabled() is True


class TestGetTelemetryEnabled:
    def test_defaults_to_false(self):
        assert app_settings_module.get_telemetry_enabled() is False

    def test_respects_stored_true(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_TELEMETRY_ENABLED, True)
        assert app_settings_module.get_telemetry_enabled() is True


class TestGetDefaultDeviceProfileName:
    def test_defaults_to_empty_string(self):
        assert app_settings_module.get_default_device_profile_name() == ""

    def test_respects_stored_value(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_DEFAULT_DEVICE_PROFILE, "RFID Reader")
        assert app_settings_module.get_default_device_profile_name() == "RFID Reader"
