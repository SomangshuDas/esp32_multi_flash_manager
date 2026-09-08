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
from app.utilities.app_settings import get_max_parallel_flashes
from app.utilities.constants import STATUS_CANCELLED, STATUS_QUEUED, STATUS_WAITING
from app.utilities.read_output_parser import extract_mac_address
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

    def __init__(self, parent: QObject | None = None, *, max_parallel: int | None = None) -> None:
        super().__init__(parent)
        # Reliability: FlashController.start_batch() used to launch one
        # QThread + one esptool subprocess per device with no limit, so a
        # very large batch (dozens or more) fired all of them at once,
        # risking OS thread, file-descriptor, or USB-bandwidth exhaustion
        # instead of queuing. Devices beyond the parallel-flash cap are
        # now held in _queue (STATUS_QUEUED) and launched one-for-one as
        # running workers finish. `max_parallel` overrides the
        # user-configurable setting (see app_settings.get_max_parallel_flashes)
        # -- mainly useful for tests that want a deterministic cap.
        self._max_parallel_override = max_parallel
        self._queue: list[DeviceConfig] = []
        self._workers: dict[str, FlashWorker] = {}
        # Authoritative busy state, set/cleared by the controller itself
        # on the main thread (see _launch_worker/_on_worker_finished).
        # QThread.isRunning() is *not* safe to rely on for this: it is
        # cleared only once the underlying OS thread has fully torn down,
        # which can happen slightly *after* the finished_flash signal
        # (queued cross-thread) has already been delivered and processed
        # here -- so a check made right after batch_finished/device_finished
        # could still observe isRunning() == True for a worker that has,
        # from every observable-from-the-controller point of view, already
        # finished. Falls back to worker.isRunning() when a device_id has
        # no entry yet (e.g. a worker injected directly for testing).
        self._busy: dict[str, bool] = {}
        self._batch_size = 0
        self._batch_results: dict[str, bool] = {}
        self._batch_start_time: float = 0.0
        # Device Traceability: first MAC address seen in each device's own
        # log output for its CURRENT flash run (esptool prints "MAC: ..."
        # during connect on every command, including write_flash) --
        # cleared per-device once a HistoryEntry has consumed it.
        self._device_macs: dict[str, str] = {}

    # ------------------------------------------------------------------
    def _resolve_max_parallel(self) -> int:
        if self._max_parallel_override is not None:
            return max(1, self._max_parallel_override)
        return get_max_parallel_flashes()

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
        """Launch one FlashWorker thread per device, up to the parallel-flash
        cap (see app_settings.get_max_parallel_flashes); any remaining
        devices are queued (STATUS_QUEUED) and launched one-for-one as
        running workers finish, instead of all firing at once."""
        eligible = [d for d in devices if not self.is_busy(d.id)]
        if not eligible:
            return

        self._batch_size = len(eligible)
        self._batch_results = {}
        self._batch_start_time = time.monotonic()
        self.batch_started.emit(self._batch_size)

        max_parallel = self._resolve_max_parallel()
        to_launch, to_queue = eligible[:max_parallel], eligible[max_parallel:]
        logger.info(
            "Starting parallel flash batch: %d device(s) (%d launched now, %d queued, cap=%d)",
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
                logger.info("Cancel requested for queued device %s", device_id)
                self._finish_queued_device(device, cancelled=True)
                return
        worker = self._workers.get(device_id)
        if worker is not None and worker.isRunning():
            logger.info("Cancel requested for device %s", device_id)
            worker.request_cancel()

    def cancel_all(self) -> None:
        for device in list(self._queue):
            self.cancel(device.id)
        for device_id in list(self._workers.keys()):
            self.cancel(device_id)

    # ------------------------------------------------------------------
    def _finish_queued_device(self, device: DeviceConfig, *, cancelled: bool) -> None:
        """Resolve a device that never got a worker launched because it was
        cancelled while still sitting in the parallel-flash queue."""
        device_id = device.id
        device.runtime.status = STATUS_CANCELLED
        self.device_status_changed.emit(device_id, STATUS_CANCELLED)
        message = "Cancelled while queued (parallel-flash limit)."
        self.device_finished.emit(device_id, False, message, 0.0)
        self._batch_results[device_id] = False
        entry = HistoryEntry.create(
            device.name, device.com_port,
            ", ".join(f.file_name for f in device.enabled_firmware()),
            0.0, "Cancelled", device_id=device_id, mac_address="",
        )
        self.history_entry_created.emit(entry)
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
            logger.info("Batch finished: %d succeeded, %d failed", succeeded, failed)
            self.batch_finished.emit(succeeded, failed)

    # ------------------------------------------------------------------
    def _launch_worker(self, device: DeviceConfig) -> None:
        self._device_macs.pop(device.id, None)
        worker = FlashWorker(device)
        worker.status_changed.connect(self.device_status_changed)
        worker.progress_changed.connect(self.device_progress_changed)
        worker.speed_changed.connect(self.device_speed_changed)
        worker.log_line.connect(self.device_log_line)
        worker.log_line.connect(self._capture_mac_from_log)
        worker.finished_flash.connect(self._on_worker_finished)
        self._workers[device.id] = worker
        self._busy[device.id] = True
        worker.start()

    def _capture_mac_from_log(self, device_id: str, line: str) -> None:
        """Device Traceability: opportunistically pull the MAC address out
        of a device's own live log output as it streams in, reusing the
        exact same parsing helper the Read Flash/eFuse Chip Info panel is
        built on (see app/utilities/read_output_parser.extract_mac_address).
        Only the first match per run is kept."""
        if device_id in self._device_macs:
            return
        mac = extract_mac_address(line)
        if mac:
            self._device_macs[device_id] = mac

    def _on_worker_finished(self, device_id: str, success: bool, message: str, duration: float) -> None:
        # Flip busy state first, before emitting anything: any slot
        # listening on device_finished/batch_finished (e.g. is_busy()
        # checks made from a signal handler) must see the device as no
        # longer busy, regardless of how long the underlying QThread
        # itself takes to actually finish tearing down.
        self._busy[device_id] = False
        self.device_finished.emit(device_id, success, message, duration)
        self._batch_results[device_id] = success

        worker = self._workers.get(device_id)
        if worker is not None:
            # Reliability: finished_flash is emitted from inside run() a
            # few instructions before the background QThread's OS thread
            # actually exits, so this slot (delivered via a queued
            # cross-thread connection) can start running on the main
            # thread slightly *before* that OS thread has fully unwound
            # and torn down. Left alone, the worker object then has
            # nothing keeping it alive but this controller's own
            # lifetime; once the controller itself goes out of scope
            # (e.g. between tests, or when a dialog closes), the
            # still-finishing QThread can end up racing whatever runs
            # next -- the exact class of bug documented on FlashWorker's
            # own __init__ (a background thread touching os.environ via
            # AppSettings/get_app_data_dir at the same moment the main
            # thread mutates it), just from the "leftover thread" angle
            # instead of the "read during run()" angle. wait() blocks
            # only until the thread that *just told us it's done*
            # actually finishes -- normally near-instant at this point --
            # closing that window before anything else can observe or
            # collect this worker. The bound is a safety net only (a
            # worker that already emitted finished_flash should never
            # legitimately take this long to unwind); a timeout is
            # logged, not raised, so a slow teardown can never turn into
            # a hung UI.
            if not worker.wait(5000):
                logger.warning(
                    "FlashWorker for device %s did not fully terminate within 5s of "
                    "finished_flash; continuing anyway.", device_id,
                )
        device_name = worker.device.name if worker else device_id
        com_port = worker.device.com_port if worker else ""
        firmware_summary = (
            ", ".join(f.file_name for f in worker.device.enabled_firmware())
            if worker else ""
        )
        result = "Completed" if success else ("Cancelled" if "Cancelled" in message else "Failed")
        mac_address = self._device_macs.pop(device_id, "")
        entry = HistoryEntry.create(
            device_name, com_port, firmware_summary, duration, result,
            device_id=device_id, mac_address=mac_address,
        )
        self.history_entry_created.emit(entry)

        # A slot the finished worker frees up: pull the next queued device
        # (if any) into it before checking whether the whole batch is done,
        # so batch_finished only fires once every queued device has also
        # actually had a chance to run.
        self._launch_next_queued()
        self._maybe_finish_batch()

    def failed_device_ids(self) -> list[str]:
        return [did for did, ok in self._batch_results.items() if not ok]
