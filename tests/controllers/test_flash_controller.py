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


class TestParallelFlashCap:
    """
    Reliability fix: FlashController.start_batch() used to launch one
    QThread + one esptool subprocess per device with no limit, so a very
    large batch fired all of them at once instead of queuing. These are
    fast, worker-free unit tests of the queue bookkeeping itself; see
    tests/workers/test_flash_worker_e2e.py::TestParallelFlashCapEndToEnd
    for the version that drives real (mocked-serial) FlashWorker threads.
    """

    def test_default_cap_matches_settings_default(self, controller):
        from app.utilities.constants import MAX_PARALLEL_FLASHES

        assert controller._resolve_max_parallel() == MAX_PARALLEL_FLASHES

    def test_override_cap_is_respected(self, qtbot):
        from app.controllers.flash_controller import FlashController

        capped = FlashController(max_parallel=3)
        assert capped._resolve_max_parallel() == 3

    def test_override_cap_clamped_to_at_least_one(self, qtbot):
        from app.controllers.flash_controller import FlashController

        capped = FlashController(max_parallel=0)
        assert capped._resolve_max_parallel() == 1

    def test_queued_device_with_no_worker_counts_as_busy(self, controller):
        device = DeviceConfig(name="Queued", com_port="COM9", chip_type="esp32")
        controller._queue.append(device)
        assert controller.is_busy(device.id) is True
        assert controller.any_busy() is True

    def test_cancelling_a_queued_device_marks_it_cancelled_and_records_history(self, qtbot, controller):
        from app.utilities.constants import STATUS_CANCELLED

        device = DeviceConfig(name="Queued", com_port="COM9", chip_type="esp32")
        controller._batch_size = 1
        controller._queue.append(device)

        with qtbot.waitSignal(controller.history_entry_created, timeout=1000):
            controller.cancel(device.id)

        assert device.runtime.status == STATUS_CANCELLED
        assert device.id not in [d.id for d in controller._queue]
        assert controller.failed_device_ids() == [device.id]
