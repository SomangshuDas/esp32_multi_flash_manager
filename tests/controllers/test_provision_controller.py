"""
pytest-qt tests for app/controllers/provision_controller.py. Mirrors
tests/controllers/test_flash_controller.py's split: fast, worker-free
unit tests of the cap/queue bookkeeping here, plus a couple of tests
that drive a fake (but real QThread-based) ProvisionWorker stand-in to
exercise the actual launch -> finish -> next-queued sequencing end to
end without touching real espefuse subprocesses.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThread, Signal

from app.controllers.provision_controller import ProvisionController
from app.models.device_model import DeviceConfig
from app.utilities.constants import STATUS_CANCELLED


@pytest.fixture
def controller(qtbot):
    return ProvisionController()


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
        controller.cancel("never-started")

    def test_cancel_all_with_no_workers_is_noop(self, controller):
        controller.cancel_all()


class TestFailedDeviceIds:
    def test_empty_before_any_batch(self, controller):
        assert controller.failed_device_ids() == []


class TestParallelProvisionCap:
    """
    Batch-provisioning gap fix: before ProvisionController existed,
    provisioning only ever ran one device at a time (one ProvisionDialog
    per device). These are fast, worker-free unit tests of the queue
    bookkeeping itself, mirroring FlashController's TestParallelFlashCap.
    """

    def test_default_cap_matches_settings_default(self, controller):
        from app.utilities.constants import MAX_PARALLEL_PROVISIONS

        assert controller._resolve_max_parallel() == MAX_PARALLEL_PROVISIONS

    def test_override_cap_is_respected(self, qtbot):
        capped = ProvisionController(max_parallel=2)
        assert capped._resolve_max_parallel() == 2

    def test_override_cap_clamped_to_at_least_one(self, qtbot):
        capped = ProvisionController(max_parallel=0)
        assert capped._resolve_max_parallel() == 1

    def test_queued_device_with_no_worker_counts_as_busy(self, controller):
        device = DeviceConfig(name="Queued", com_port="COM9", chip_type="esp32")
        controller._queue.append(device)
        assert controller.is_busy(device.id) is True
        assert controller.any_busy() is True

    def test_cancelling_a_queued_device_marks_it_cancelled(self, qtbot, controller):
        device = DeviceConfig(name="Queued", com_port="COM9", chip_type="esp32")
        controller._batch_size = 1
        controller._queue.append(device)

        with qtbot.waitSignal(controller.batch_finished, timeout=1000):
            controller.cancel(device.id)

        assert device.runtime.status == STATUS_CANCELLED
        assert device.id not in [d.id for d in controller._queue]
        assert controller.failed_device_ids() == [device.id]


class _FakeProvisionWorker(QThread):
    """Minimal stand-in for security_worker.ProvisionWorker: finishes
    almost immediately (success unless the device's name contains
    'fail'), without touching any real subprocess/hardware."""

    status_changed = Signal(str, str)
    log_line = Signal(str, str)
    finished_provision = Signal(str, bool, str, float)

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.device = device
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        if self._cancel_requested:
            self.finished_provision.emit(self.device.id, False, "Cancelled.", 0.0)
            return
        success = "fail" not in self.device.name.lower()
        self.finished_provision.emit(self.device.id, success, "done", 0.01)


class TestEndToEndWithFakeWorker:
    @staticmethod
    def _drain(controller):
        # Ensure every QThread this controller ever launched has fully
        # torn down before the test returns -- otherwise a worker whose
        # finished_provision signal already fired but whose underlying
        # OS thread hasn't wound down yet can get garbage-collected
        # mid-run, which aborts the whole test process (see
        # FlashController's own notes on why isRunning() alone isn't a
        # safe cross-thread readiness check).
        for worker in controller._workers.values():
            worker.wait(2000)

    def test_batch_of_two_under_default_cap_both_complete(self, qtbot, monkeypatch):
        import app.controllers.provision_controller as provision_controller_module

        monkeypatch.setattr(provision_controller_module, "ProvisionWorker", _FakeProvisionWorker)
        controller = ProvisionController(max_parallel=4)
        device_a = DeviceConfig(name="A", com_port="COM3", chip_type="esp32")
        device_b = DeviceConfig(name="B", com_port="COM4", chip_type="esp32")

        with qtbot.waitSignal(controller.batch_finished, timeout=3000) as blocker:
            controller.start_batch([device_a, device_b])
        self._drain(controller)

        succeeded, failed = blocker.args
        assert succeeded == 2
        assert failed == 0
        assert controller.any_busy() is False

    def test_cap_of_one_queues_second_device_then_runs_it(self, qtbot, monkeypatch):
        import app.controllers.provision_controller as provision_controller_module

        monkeypatch.setattr(provision_controller_module, "ProvisionWorker", _FakeProvisionWorker)
        controller = ProvisionController(max_parallel=1)
        device_a = DeviceConfig(name="A", com_port="COM3", chip_type="esp32")
        device_b = DeviceConfig(name="B", com_port="COM4", chip_type="esp32")

        with qtbot.waitSignal(controller.batch_finished, timeout=3000) as blocker:
            controller.start_batch([device_a, device_b])
        self._drain(controller)

        succeeded, failed = blocker.args
        assert succeeded == 2
        assert failed == 0

    def test_failing_device_is_reflected_in_failed_device_ids(self, qtbot, monkeypatch):
        import app.controllers.provision_controller as provision_controller_module

        monkeypatch.setattr(provision_controller_module, "ProvisionWorker", _FakeProvisionWorker)
        controller = ProvisionController(max_parallel=4)
        device = DeviceConfig(name="will-fail", com_port="COM3", chip_type="esp32")

        with qtbot.waitSignal(controller.batch_finished, timeout=3000) as blocker:
            controller.start_batch([device])
        self._drain(controller)

        succeeded, failed = blocker.args
        assert succeeded == 0
        assert failed == 1
        assert controller.failed_device_ids() == [device.id]
