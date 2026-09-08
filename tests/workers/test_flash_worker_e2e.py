"""
Mocked-serial end-to-end test for the flashing pipeline.

This drives the REAL production code (FlashWorker.run(), its QThread
lifecycle, parse_progress_line(), FlashController's signal wiring and
HistoryEntry creation) but replaces `FlashProcess` -- the one class that
actually launches a subprocess and talks to a serial port -- with a fake
that plays back a scripted sequence of esptool-style stdout lines. No
real hardware, esptool binary, or serial port is touched.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.controllers.flash_controller import FlashController
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONNECTING,
    STATUS_FAILED,
)
from app.workers import flash_worker as flash_worker_module


def make_fake_flash_process(lines, return_code=0, block_after: int | None = None):
    """
    Build a fake FlashProcess class that plays back `lines` through
    iter_lines() exactly like a real esptool session would, then reports
    `return_code` from wait().

    If `block_after` is given, iter_lines() blocks (simulating a hung
    subprocess) after yielding that many lines until terminate() is
    called -- used to exercise the cancel path deterministically.
    """

    class FakeFlashProcess:
        def __init__(self, command):
            self.command = command
            self._terminated = threading.Event()
            self._return_code = return_code

        def start(self) -> None:
            pass

        def iter_lines(self, stall_timeout=None):
            for i, line in enumerate(lines):
                if block_after is not None and i == block_after:
                    self._terminated.wait(timeout=5)
                    return
                yield line

        def wait(self, timeout=None) -> int:
            return self._return_code

        def terminate(self) -> None:
            self._terminated.set()

    return FakeFlashProcess


@pytest.fixture
def device(tmp_path) -> DeviceConfig:
    firmware_path = tmp_path / "firmware.bin"
    firmware_path.write_bytes(b"\x00" * 4096)
    device = DeviceConfig(name="Bench 1", com_port="COM3", chip_type="esp32")
    entry = FirmwareEntry(file_path=str(firmware_path), address="0x10000")
    entry.refresh()
    device.add_firmware(entry)
    return device


@pytest.fixture
def controller(qtbot):
    return FlashController()


SUCCESSFUL_SESSION_LINES = [
    "Serial port COM3",
    "Connecting....",
    "Chip is ESP32-D0WDQ6 (revision 1)",
    "Erasing flash (this may take a while)...",
    "Chip erase completed successfully",
    "Writing at 0x00010000... (50 %)",
    "Writing at 0x00010000... (100 %)",
    "Wrote 4096 bytes",
    "Hash of data verified.",
    "Hard resetting via RTS pin...",
]

PORT_LOST_SESSION_LINES = [
    "Serial port COM3",
    "Connecting....",
    "A fatal error occurred: Failed to connect to ESP32: No serial data received.",
]


class TestMockedSerialEndToEndSuccess:
    def test_full_connect_flash_verify_cycle_reports_completed(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0),
        )

        statuses: list[str] = []
        controller.device_status_changed.connect(lambda dev_id, status: statuses.append(status))

        with qtbot.waitSignal(controller.batch_finished, timeout=5000) as blocker:
            controller.start_batch([device])

        succeeded, failed = blocker.args
        assert succeeded == 1
        assert failed == 0
        assert STATUS_CONNECTING in statuses
        assert STATUS_COMPLETED in statuses
        assert controller.failed_device_ids() == []

    def test_progress_and_speed_signals_fire_during_write(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0),
        )

        progress_updates = []
        controller.device_progress_changed.connect(lambda dev_id, pct, addr: progress_updates.append(pct))

        with qtbot.waitSignal(controller.batch_finished, timeout=5000):
            controller.start_batch([device])

        assert 50 in progress_updates
        assert 100 in progress_updates  # from the writing line and/or the final 100% on success

    def test_history_entry_created_on_success(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0),
        )

        with qtbot.waitSignal(controller.history_entry_created, timeout=5000) as blocker:
            controller.start_batch([device])

        entry = blocker.args[0]
        assert entry.device_name == "Bench 1"
        assert entry.com_port == "COM3"
        assert entry.result == "Completed"

    def test_is_busy_true_during_run_false_after(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0, block_after=2),
        )
        controller.start_batch([device])
        # Give the worker thread a moment to actually start and block.
        qtbot.wait(100)
        assert controller.is_busy(device.id) is True
        assert controller.any_busy() is True
        controller.cancel(device.id)
        qtbot.waitSignal(controller.batch_finished, timeout=5000).wait()
        assert controller.is_busy(device.id) is False


class TestMockedSerialEndToEndFailure:
    def test_port_lost_reports_failed_with_actionable_message(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(PORT_LOST_SESSION_LINES, return_code=1),
        )

        statuses: list[str] = []
        controller.device_status_changed.connect(lambda dev_id, status: statuses.append(status))

        with qtbot.waitSignal(controller.device_finished, timeout=5000) as blocker:
            controller.start_batch([device])

        device_id, success, message, duration = blocker.args
        assert success is False
        assert "No serial data received" in message
        assert STATUS_FAILED in statuses
        assert controller.failed_device_ids() == [device.id]

    def test_batch_finished_counts_failure_correctly(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(PORT_LOST_SESSION_LINES, return_code=1),
        )
        with qtbot.waitSignal(controller.batch_finished, timeout=5000) as blocker:
            controller.start_batch([device])
        succeeded, failed = blocker.args
        assert succeeded == 0
        assert failed == 1

    def test_history_entry_created_on_failure(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(PORT_LOST_SESSION_LINES, return_code=1),
        )
        with qtbot.waitSignal(controller.history_entry_created, timeout=5000) as blocker:
            controller.start_batch([device])
        entry = blocker.args[0]
        assert entry.result == "Failed"


class TestMockedSerialEndToEndCancel:
    def test_cancel_mid_flash_reports_cancelled(self, qtbot, monkeypatch, controller, device):
        # Block after 2 lines so the test can request a cancel while the
        # worker thread is still "connected" and waiting for more output,
        # exactly like cancelling a real in-progress upload.
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0, block_after=2),
        )

        controller.start_batch([device])
        qtbot.wait(100)  # let the worker thread reach the blocking point
        assert controller.is_busy(device.id) is True

        with qtbot.waitSignal(controller.device_finished, timeout=5000) as blocker:
            controller.cancel(device.id)

        device_id, success, message, duration = blocker.args
        assert success is False
        assert "Cancelled" in message

    def test_cancel_all_cancels_every_running_device(self, qtbot, monkeypatch, controller, tmp_path):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0, block_after=2),
        )
        device_a = DeviceConfig(name="A", com_port="COM3", chip_type="esp32")
        device_b = DeviceConfig(name="B", com_port="COM4", chip_type="esp32")
        for d in (device_a, device_b):
            fw_path = tmp_path / f"{d.name}.bin"
            fw_path.write_bytes(b"\x00" * 16)
            entry = FirmwareEntry(file_path=str(fw_path), address="0x10000")
            entry.refresh()
            d.add_firmware(entry)

        with qtbot.waitSignal(controller.batch_started, timeout=5000):
            controller.start_batch([device_a, device_b])
        qtbot.wait(100)

        with qtbot.waitSignal(controller.batch_finished, timeout=5000) as blocker:
            controller.cancel_all()

        succeeded, failed = blocker.args
        assert succeeded == 0
        assert failed == 2


class TestWorkerThreadFullyStoppedOnFinish:
    """
    Reliability fix: finished_flash is emitted from inside FlashWorker.run()
    a few instructions before the QThread's OS thread actually exits, so a
    caller reacting to device_finished/batch_finished used to have no
    guarantee the thread had truly stopped -- a still-finishing QThread with
    nothing else keeping it alive could then be raced by whatever ran next
    (a real, reproducible CI crash: Fatal Python error: Aborted). Both these
    tests assert on isRunning() with NO extra qtbot.wait() cushion, so a
    regression here (removing the worker.wait() call in
    FlashController._on_worker_finished) would flip them back to flaky/fail.
    """

    def test_thread_already_stopped_when_device_finished_fires(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0),
        )
        with qtbot.waitSignal(controller.device_finished, timeout=5000):
            controller.start_batch([device])
        worker = controller._workers[device.id]
        assert worker.isRunning() is False

    def test_thread_already_stopped_when_cancelled_mid_flash(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0, block_after=2),
        )
        controller.start_batch([device])
        qtbot.wait(100)
        with qtbot.waitSignal(controller.device_finished, timeout=5000):
            controller.cancel(device.id)
        worker = controller._workers[device.id]
        assert worker.isRunning() is False


class TestBusyGuardDuringBatch:
    def test_start_batch_skips_devices_already_busy(self, qtbot, monkeypatch, controller, device):
        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0, block_after=2),
        )
        controller.start_batch([device])
        qtbot.wait(100)
        assert controller.is_busy(device.id) is True

        # Re-issuing a batch that includes an already-busy device must not
        # launch a second worker for it (that would be two subprocesses
        # racing on the same serial port).
        with qtbot.assertNotEmitted(controller.batch_started, wait=200):
            controller.start_batch([device])

        controller.cancel_all()
        qtbot.waitSignal(controller.batch_finished, timeout=5000).wait()


def _make_device(tmp_path, name, com_port):
    fw_path = tmp_path / f"{name}.bin"
    fw_path.write_bytes(b"\x00" * 16)
    device = DeviceConfig(name=name, com_port=com_port, chip_type="esp32")
    entry = FirmwareEntry(file_path=str(fw_path), address="0x10000")
    entry.refresh()
    device.add_firmware(entry)
    return device


class TestParallelFlashCapEndToEnd:
    """
    Reliability fix: FlashController.start_batch() used to launch one
    QThread + one esptool subprocess per device with no limit. These drive
    real FlashWorker QThreads (mocked serial, as in the rest of this file)
    against a FlashController capped to 1 concurrent device.
    """

    def test_second_device_is_queued_then_launched_once_the_first_finishes(self, qtbot, monkeypatch, tmp_path):
        from app.controllers.flash_controller import FlashController
        from app.utilities.constants import STATUS_QUEUED

        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0, block_after=2),
        )
        controller = FlashController(max_parallel=1)
        device_a = _make_device(tmp_path, "A", "COM3")
        device_b = _make_device(tmp_path, "B", "COM4")

        with qtbot.waitSignal(controller.batch_started, timeout=5000):
            controller.start_batch([device_a, device_b])
        qtbot.wait(100)

        # Only the cap's worth of devices actually get a worker; the rest
        # sit in the queue (STATUS_QUEUED) but still read as busy so a
        # second start_batch() call can't double-launch them.
        assert device_b.runtime.status == STATUS_QUEUED
        assert controller.is_busy(device_a.id) is True
        assert controller.is_busy(device_b.id) is True

        with qtbot.waitSignal(controller.batch_finished, timeout=5000) as blocker:
            controller.cancel_all()

        succeeded, failed = blocker.args
        assert succeeded == 0
        assert failed == 2  # A cancelled mid-flash, B cancelled while queued

    def test_all_devices_eventually_complete_despite_cap_of_one(self, qtbot, monkeypatch, tmp_path):
        from app.controllers.flash_controller import FlashController

        monkeypatch.setattr(
            flash_worker_module, "FlashProcess",
            make_fake_flash_process(SUCCESSFUL_SESSION_LINES, return_code=0),
        )
        controller = FlashController(max_parallel=1)
        device_a = _make_device(tmp_path, "A", "COM3")
        device_b = _make_device(tmp_path, "B", "COM4")

        with qtbot.waitSignal(controller.batch_finished, timeout=5000) as blocker:
            controller.start_batch([device_a, device_b])

        succeeded, failed = blocker.args
        assert succeeded == 2
        assert failed == 0
        assert controller.is_busy(device_a.id) is False
        assert controller.is_busy(device_b.id) is False
