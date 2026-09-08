"""
provision_controller.py
========================
Orchestrates BATCH/multi-device provisioning (eFuse burning): spins up one
ProvisionWorker QThread per device, relays its signals up to the UI (see
app/ui/batch_provision_dialog.py), and applies the same cap/queue design
FlashController uses for parallel flashing (see app/controllers/
flash_controller.py) -- devices beyond the configured parallel-provision
cap (app.utilities.app_settings.get_max_parallel_provisions) are held in
a FIFO queue (STATUS_QUEUED) and launched one-for-one as running workers
finish, instead of firing every requested burn at once.

Before this controller existed, provisioning only had a single-device
path (app/ui/provision_dialog.py, driving exactly one ProvisionWorker),
so burning a production batch with security enabled required opening
that dialog, confirming, and waiting once per device by hand.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.app_settings import get_max_parallel_provisions
from app.utilities.constants import STATUS_CANCELLED, STATUS_QUEUED, STATUS_WAITING
from app.workers.security_worker import ProvisionWorker

logger = get_logger(__name__)


class ProvisionController(QObject):
    """
    Signals
    -------
    device_status_changed(device_id, status)
    device_log_line(device_id, line)
    device_finished(device_id, success, message, duration)
    batch_started(int)              - number of devices in this batch
    batch_finished(int, int)        - (succeeded_count, failed_count)
    """

    device_status_changed = Signal(str, str)
    device_log_line = Signal(str, str)
    device_finished = Signal(str, bool, str, float)
    batch_started = Signal(int)
    batch_finished = Signal(int, int)

    def __init__(self, parent: QObject | None = None, *, max_parallel: int | None = None) -> None:
        super().__init__(parent)
        # `max_parallel` overrides the user-configurable setting (see
        # app_settings.get_max_parallel_provisions) -- mainly useful for
        # tests that want a deterministic cap, mirroring FlashController.
        self._max_parallel_override = max_parallel
        self._queue: list[DeviceConfig] = []
        self._workers: dict[str, ProvisionWorker] = {}
        # Authoritative busy state, set/cleared by the controller itself on
        # the main thread -- see FlashController for why this is safer than
        # trusting QThread.isRunning() alone.
        self._busy: dict[str, bool] = {}
        self._batch_size = 0
        self._batch_results: dict[str, bool] = {}

    # ------------------------------------------------------------------
    def _resolve_max_parallel(self) -> int:
        if self._max_parallel_override is not None:
            return max(1, self._max_parallel_override)
        return get_max_parallel_provisions()

    def is_busy(self, device_id: str) -> bool:
        if any(device.id == device_id for device in self._queue):
            return True
        worker = self._workers.get(device_id)
        if worker is None:
            return False
        if device_id in self._busy:
            return self._busy[device_id]
        return worker.isRunning()

    def any_busy(self) -> bool:
        if self._queue:
            return True
        return any(self.is_busy(device_id) for device_id in self._workers)

    # ------------------------------------------------------------------
    def start_batch(self, devices: list[DeviceConfig]) -> None:
        """Launch one ProvisionWorker thread per device, up to the
        parallel-provision cap; any remaining devices are queued
        (STATUS_QUEUED) and launched one-for-one as running workers
        finish. Callers are responsible for pre-flight validation and
        the irreversible-burn confirmation gate (see
        app/ui/batch_provision_dialog.py) -- this controller only
        sequences already-approved burns."""
        eligible = [d for d in devices if not self.is_busy(d.id)]
        if not eligible:
            return

        self._batch_size = len(eligible)
        self._batch_results = {}
        self.batch_started.emit(self._batch_size)

        max_parallel = self._resolve_max_parallel()
        to_launch, to_queue = eligible[:max_parallel], eligible[max_parallel:]
        logger.info(
            "Starting batch provisioning: %d device(s) (%d launched now, %d queued, cap=%d)",
            self._batch_size, len(to_launch), len(to_queue), max_parallel,
        )

        for device in to_queue:
            device.runtime.status = STATUS_QUEUED
            self._queue.append(device)
        for device in to_launch:
            device.runtime.status = STATUS_WAITING
            self._launch_worker(device)

    def start_single(self, device: DeviceConfig) -> None:
        self.start_batch([device])

    def cancel(self, device_id: str) -> None:
        for index, device in enumerate(self._queue):
            if device.id == device_id:
                del self._queue[index]
                logger.info("Cancel requested for queued provisioning device %s", device_id)
                self._finish_queued_device(device)
                return
        worker = self._workers.get(device_id)
        if worker is not None and worker.isRunning():
            logger.info("Cancel requested for provisioning device %s", device_id)
            worker.request_cancel()

    def cancel_all(self) -> None:
        for device in list(self._queue):
            self.cancel(device.id)
        for device_id in list(self._workers.keys()):
            self.cancel(device_id)

    # ------------------------------------------------------------------
    def _finish_queued_device(self, device: DeviceConfig) -> None:
        """Resolve a device that never got a worker launched because it was
        cancelled while still sitting in the parallel-provision queue."""
        device_id = device.id
        device.runtime.status = STATUS_CANCELLED
        self.device_status_changed.emit(device_id, STATUS_CANCELLED)
        message = "Cancelled while queued (parallel-provision limit)."
        self.device_finished.emit(device_id, False, message, 0.0)
        self._batch_results[device_id] = False
        # Note: unlike _on_worker_finished, this does NOT free up a running
        # slot (the device never had a worker), so it must not trigger
        # _launch_next_queued() -- doing so would exceed the parallel cap.
        self._maybe_finish_batch()

    def _launch_next_queued(self) -> None:
        if not self._queue:
            return
        device = self._queue.pop(0)
        device.runtime.status = STATUS_WAITING
        self._launch_worker(device)

    def _maybe_finish_batch(self) -> None:
        if len(self._batch_results) >= self._batch_size:
            succeeded = sum(1 for ok in self._batch_results.values() if ok)
            failed = self._batch_size - succeeded
            logger.info("Batch provisioning finished: %d succeeded, %d failed", succeeded, failed)
            self.batch_finished.emit(succeeded, failed)

    # ------------------------------------------------------------------
    def _launch_worker(self, device: DeviceConfig) -> None:
        worker = ProvisionWorker(device)
        worker.status_changed.connect(self.device_status_changed)
        worker.log_line.connect(self.device_log_line)
        worker.finished_provision.connect(self._on_worker_finished)
        self._workers[device.id] = worker
        self._busy[device.id] = True
        worker.start()

    def _on_worker_finished(self, device_id: str, success: bool, message: str, duration: float) -> None:
        # Flip busy state first, before emitting anything -- see
        # FlashController._on_worker_finished for why.
        self._busy[device_id] = False
        self.device_finished.emit(device_id, success, message, duration)
        self._batch_results[device_id] = success

        # Reliability: mirrors FlashController._on_worker_finished's own
        # worker.wait() -- finished_provision is emitted from inside
        # run() a few instructions before the background QThread's OS
        # thread actually exits, so left unjoined this worker can race
        # whatever runs next once nothing but this controller keeps it
        # alive. wait() blocks only until the thread that just told us
        # it's done actually finishes -- normally near-instant here --
        # and a timeout is logged, not raised, so a slow teardown can
        # never hang the UI.
        worker = self._workers.get(device_id)
        if worker is not None and not worker.wait(5000):
            logger.warning(
                "ProvisionWorker for device %s did not fully terminate within 5s of "
                "finished_provision; continuing anyway.", device_id,
            )

        # A slot the finished worker frees up: pull the next queued device
        # (if any) into it before checking whether the whole batch is done.
        self._launch_next_queued()
        self._maybe_finish_batch()

    def failed_device_ids(self) -> list[str]:
        return [did for did, ok in self._batch_results.items() if not ok]
