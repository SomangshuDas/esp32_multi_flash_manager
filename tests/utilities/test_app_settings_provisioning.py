"""
Tests for the batch-provisioning-related settings getters added to
app/utilities/app_settings.py: get_max_parallel_provisions() and
get_provision_stall_timeout_seconds(). Mirrors the existing (untested
before this) get_max_parallel_flashes()/get_flash_stall_timeout_seconds()
shape, so these are exercised the same way going forward.
"""

from __future__ import annotations

import pytest

import app.utilities.app_settings as app_settings_module
from app.utilities.constants import (
    MAX_PARALLEL_PROVISIONS,
    MAX_PARALLEL_PROVISIONS_MAX,
    MAX_PARALLEL_PROVISIONS_MIN,
    PROVISION_STALL_TIMEOUT_MAX_SECONDS,
    PROVISION_STALL_TIMEOUT_MIN_SECONDS,
    PROVISION_STALL_TIMEOUT_SECONDS,
    SETTINGS_KEY_MAX_PARALLEL_PROVISIONS,
    SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS,
)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Point AppSettings at a throwaway directory and reset the
    process-wide singleton so each test starts from a clean slate,
    independent of any real settings.json on the host running the
    tests."""
    monkeypatch.setattr(app_settings_module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_settings_module, "_instance", None)
    yield
    monkeypatch.setattr(app_settings_module, "_instance", None)


class TestGetMaxParallelProvisions:
    def test_defaults_when_unset(self):
        assert app_settings_module.get_max_parallel_provisions() == MAX_PARALLEL_PROVISIONS

    def test_respects_stored_value(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_MAX_PARALLEL_PROVISIONS, 7)
        assert app_settings_module.get_max_parallel_provisions() == 7

    def test_clamped_to_max(self):
        app_settings_module.get_settings().setValue(
            SETTINGS_KEY_MAX_PARALLEL_PROVISIONS, MAX_PARALLEL_PROVISIONS_MAX + 100
        )
        assert app_settings_module.get_max_parallel_provisions() == MAX_PARALLEL_PROVISIONS_MAX

    def test_clamped_to_min(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_MAX_PARALLEL_PROVISIONS, -5)
        assert app_settings_module.get_max_parallel_provisions() == MAX_PARALLEL_PROVISIONS_MIN

    def test_corrupted_value_falls_back_to_default(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_MAX_PARALLEL_PROVISIONS, "not-a-number")
        assert app_settings_module.get_max_parallel_provisions() == MAX_PARALLEL_PROVISIONS


class TestGetProvisionStallTimeoutSeconds:
    def test_defaults_when_unset(self):
        assert app_settings_module.get_provision_stall_timeout_seconds() == PROVISION_STALL_TIMEOUT_SECONDS

    def test_respects_stored_value(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS, 90.0)
        assert app_settings_module.get_provision_stall_timeout_seconds() == 90.0

    def test_clamped_to_max(self):
        app_settings_module.get_settings().setValue(
            SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS, PROVISION_STALL_TIMEOUT_MAX_SECONDS + 500
        )
        assert app_settings_module.get_provision_stall_timeout_seconds() == PROVISION_STALL_TIMEOUT_MAX_SECONDS

    def test_clamped_to_min(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS, 0.0)
        assert app_settings_module.get_provision_stall_timeout_seconds() == PROVISION_STALL_TIMEOUT_MIN_SECONDS

    def test_corrupted_value_falls_back_to_default(self):
        app_settings_module.get_settings().setValue(SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS, "nope")
        assert app_settings_module.get_provision_stall_timeout_seconds() == PROVISION_STALL_TIMEOUT_SECONDS
