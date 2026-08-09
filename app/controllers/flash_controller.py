"""
flash_controller.py
====================
Orchestrates parallel flashing: spins up one FlashWorker QThread per
device, relays their signals up to the UI (adding the device_id so the
UI can route updates to the right row), tracks overall progress, and
records completed attempts into flash history.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.models.history_model import HistoryEntry
from app.utilities.constants import STATUS_WAITING
from app.workers.flash_worker import FlashWorker

logger = get_logger(__name__)


class FlashController(QObject):
    """
    Signals
    -------
    device_status_changed(device_id, status)
    device_progress_changed(device_id, percent, address)
    device_speed_changed(device_id, kbps)
    device_log_line(device_id, line)
    device_finished(device_id, success, message, duration)
    batch_started(int)              - number of devices in this batch
    batch_finished(int, int)        - (succeeded_count, failed_count)
    history_entry_created(HistoryEntry)
    """

    device_status_changed = Signal(str, str)
    device_progress_changed = Signal(str, int, str)
    device_speed_changed = Signal(str, float)
    device_log_line = Signal(str, str)
    device_finished = Signal(str, bool, str, float)
    batch_started = Signal(int)
    batch_finished = Signal(int, int)
    history_entry_created = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workers: dict[str, FlashWorker] = {}
        self._batch_size = 0
        self._batch_results: dict[str, bool] = {}
        self._batch_start_time: float = 0.0

    # ------------------------------------------------------------------
    def is_busy(self, device_id: str) -> bool:
        worker = self._workers.get(device_id)
        return worker is not None and worker.isRunning()

    def any_busy(self) -> bool:
        return any(w.isRunning() for w in self._workers.values())

    # ------------------------------------------------------------------
    def start_batch(self, devices: list[DeviceConfig]) -> None:
        """Launch one FlashWorker thread per device, all running concurrently."""
        eligible = [d for d in devices if not self.is_busy(d.id)]
        if not eligible:
            return

        self._batch_size = len(eligible)
        self._batch_results = {}
        self._batch_start_time = time.monotonic()
        self.batch_started.emit(self._batch_size)
        logger.info("Starting parallel flash batch: %d device(s)", self._batch_size)

        for device in eligible:
            device.runtime.status = STATUS_WAITING
            self._launch_worker(device)

    def start_single(self, device: DeviceConfig) -> None:
        self.start_batch([device])

    def cancel(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if worker is not None and worker.isRunning():
            logger.info("Cancel requested for device %s", device_id)
            worker.request_cancel()

    def cancel_all(self) -> None:
        for device_id in list(self._workers.keys()):
            self.cancel(device_id)

    # ------------------------------------------------------------------
    def _launch_worker(self, device: DeviceConfig) -> None:
        worker = FlashWorker(device)
        worker.status_changed.connect(self.device_status_changed)
        worker.progress_changed.connect(self.device_progress_changed)
        worker.speed_changed.connect(self.device_speed_changed)
        worker.log_line.connect(self.device_log_line)
        worker.finished_flash.connect(self._on_worker_finished)
        self._workers[device.id] = worker
        worker.start()

    def _on_worker_finished(self, device_id: str, success: bool, message: str, duration: float) -> None:
        self.device_finished.emit(device_id, success, message, duration)
        self._batch_results[device_id] = success

        worker = self._workers.get(device_id)
        device_name = worker.device.name if worker else device_id
        com_port = worker.device.com_port if worker else ""
        firmware_summary = (
            ", ".join(f.file_name for f in worker.device.enabled_firmware())
            if worker else ""
        )
        result = "Completed" if success else ("Cancelled" if "Cancelled" in message else "Failed")
        entry = HistoryEntry.create(device_name, com_port, firmware_summary, duration, result)
        self.history_entry_created.emit(entry)

        if len(self._batch_results) >= self._batch_size:
            succeeded = sum(1 for ok in self._batch_results.values() if ok)
            failed = self._batch_size - succeeded
            logger.info("Batch finished: %d succeeded, %d failed", succeeded, failed)
            self.batch_finished.emit(succeeded, failed)

    def failed_device_ids(self) -> list[str]:
        return [did for did, ok in self._batch_results.items() if not ok]
