"""
pytest-qt tests for app/controllers/flash_controller.py that don't need a
full simulated flash session (see tests/workers/test_flash_worker_e2e.py
for the full mocked-serial connect->flash->verify pipeline).
"""

from __future__ import annotations

import pytest

from app.controllers.flash_controller import FlashController
from app.models.device_model import DeviceConfig


@pytest.fixture
def controller(qtbot):
    return FlashController()


class TestBusyTrackingWithNoWorkers:
    def test_is_busy_false_for_unknown_device(self, controller):
        assert controller.is_busy("never-started") is False

    def test_any_busy_false_when_nothing_running(self, controller):
        assert controller.any_busy() is False


class TestStartBatchEdgeCases:
    def test_empty_device_list_does_not_emit_batch_started(self, qtbot, controller):
        with qtbot.assertNotEmitted(controller.batch_started, wait=200):
            controller.start_batch([])

    def test_start_single_delegates_to_start_batch(self, qtbot, monkeypatch, controller):
        received = []
        monkeypatch.setattr(controller, "start_batch", lambda devices: received.extend(devices))
        device = DeviceConfig(name="Solo")
        controller.start_single(device)
        assert received == [device]


class TestCancelWithNoWorkers:
    def test_cancel_unknown_device_is_noop(self, controller):
        # Must not raise even though no worker was ever launched.
        controller.cancel("never-started")

    def test_cancel_all_with_no_workers_is_noop(self, controller):
        controller.cancel_all()


class TestFailedDeviceIds:
    def test_empty_before_any_batch(self, controller):
        assert controller.failed_device_ids() == []
