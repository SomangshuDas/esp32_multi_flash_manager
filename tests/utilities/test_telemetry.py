"""
Tests for app/utilities/telemetry.py: the opt-in, local-only anonymous
usage/crash telemetry recorder.
"""

from __future__ import annotations

import json

import pytest

import app.utilities.app_settings as app_settings_module
import app.utilities.telemetry as telemetry_module
from app.utilities.constants import SETTINGS_KEY_TELEMETRY_ENABLED, TELEMETRY_LOG_FILENAME


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(telemetry_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_settings_module, "_instance", None)
    yield tmp_path
    monkeypatch.setattr(app_settings_module, "_instance", None)


class TestIsEnabled:
    def test_disabled_by_default(self):
        assert telemetry_module.is_enabled() is False


class TestRecordEvent:
    def test_no_op_when_disabled(self, tmp_path):
        telemetry_module.record_event(telemetry_module.TelemetryEvent.APP_STARTED)
        assert not (tmp_path / TELEMETRY_LOG_FILENAME).exists()

    def test_writes_event_when_enabled(self, tmp_path):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_TELEMETRY_ENABLED, True)
        telemetry_module.record_event(
            telemetry_module.TelemetryEvent.FLASH_BATCH_FINISHED,
            {"device_count": 4, "succeeded": 4, "failed": 0},
        )
        path = tmp_path / TELEMETRY_LOG_FILENAME
        assert path.exists()
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "flash_batch_finished"
        assert record["data"] == {"device_count": 4, "succeeded": 4, "failed": 0}
        assert record["client_id"]  # a client id was generated

    def test_client_id_is_stable_across_events(self, tmp_path):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_TELEMETRY_ENABLED, True)
        telemetry_module.record_event(telemetry_module.TelemetryEvent.APP_STARTED)
        telemetry_module.record_event(telemetry_module.TelemetryEvent.PROJECT_OPENED)
        lines = (tmp_path / TELEMETRY_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
        ids = {json.loads(ln)["client_id"] for ln in lines if ln.strip()}
        assert len(ids) == 1

    def test_never_includes_raw_extra_keys_beyond_data(self, tmp_path):
        """Guards against a future call site accidentally passing
        identifying top-level fields -- record_event only ever writes
        the fixed (client_id, event, data, timestamp) shape."""
        app_settings_module.get_settings().setValue(SETTINGS_KEY_TELEMETRY_ENABLED, True)
        telemetry_module.record_event(telemetry_module.TelemetryEvent.APP_STARTED, {"foo": "bar"})
        record = json.loads(
            (tmp_path / TELEMETRY_LOG_FILENAME).read_text(encoding="utf-8").splitlines()[0]
        )
        assert set(record.keys()) == {"client_id", "event", "data", "timestamp"}


class TestClearLocalTelemetry:
    def test_deletes_existing_file(self, tmp_path):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_TELEMETRY_ENABLED, True)
        telemetry_module.record_event(telemetry_module.TelemetryEvent.APP_STARTED)
        assert (tmp_path / TELEMETRY_LOG_FILENAME).exists()
        telemetry_module.clear_local_telemetry()
        assert not (tmp_path / TELEMETRY_LOG_FILENAME).exists()

    def test_no_error_when_nothing_to_clear(self, tmp_path):
        telemetry_module.clear_local_telemetry()  # should not raise
