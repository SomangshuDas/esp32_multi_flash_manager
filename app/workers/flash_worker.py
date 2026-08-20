"""
flash_worker.py
================
FlashWorker runs entirely inside its own QThread and drives a single
device's esptool subprocess to completion, emitting Qt signals that the
controller/UI layer consume to update per-device progress bars, status
badges, live console output, and timers.

Each device gets exactly one FlashWorker instance per upload attempt —
this is what gives us true parallel flashing: N devices == N QThreads,
each with its own subprocess, so a slow/stuck device never blocks the
others (and the GUI thread is never touched by blocking I/O).

Expected vs. unexpected failures
---------------------------------
Every code path through run() ends at _finish() with a status and a
message — an EXPECTED upload failure (bad cable, board not in bootloader
mode, wrong port, "No serial data received", a stalled/disconnected
device, cancellation, ...) is reported as STATUS_FAILED/STATUS_CANCELLED
with a clear, actionable message shown in the device's status badge, its
Live Output console, and the flash history entry. None of that is allowed
to propagate as a raised Python exception out of run() — the outermost
try/except at the bottom of this method exists specifically so that an
unplugged board never ends up in Anthropic-style "Unexpected Error" territory
(main.py's global sys.excepthook, which is reserved for genuine bugs in
this app, not routine hardware/cabling issues every flashing session runs
into sooner or later).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from app.flash_engine.esptool_wrapper import (
    FlashCommandBuilder,
    FlashProcess,
    parse_progress_line,
)
from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.constants import (
    FLASH_STALL_TIMEOUT_SECONDS,
    STATUS_CANCELLED,
    STATUS_CONNECTING,
    STATUS_COMPLETED,
    STATUS_ERASING,
    STATUS_FAILED,
    STATUS_PREPARING,
    STATUS_UPLOADING,
    STATUS_VERIFYING,
)

logger = get_logger(__name__)


class FlashWorker(QThread):
    """
    Signals
    -------
    status_changed(device_id, status_str)
    progress_changed(device_id, percent, current_address)
    speed_changed(device_id, kbps)
    log_line(device_id, line_str)
    finished_flash(device_id, success_bool, message_str, duration_seconds)
    """

    status_changed = Signal(str, str)
    progress_changed = Signal(str, int, str)
    speed_changed = Signal(str, float)
    log_line = Signal(str, str)
    finished_flash = Signal(str, bool, str, float)

    def __init__(self, device: DeviceConfig, parent=None) -> None:
        super().__init__(parent)
        self.device = device
        self._process: FlashProcess | None = None
        self._cancel_requested = False
        self._last_progress_bytes_time: float | None = None

    # ------------------------------------------------------------------
    def request_cancel(self) -> None:
        """Thread-safe-ish cancel request; polled by run() and also used
        to actively kill the running subprocess for immediate response."""
        self._cancel_requested = True
        if self._process is not None:
            self._process.terminate()

    # ------------------------------------------------------------------
    def run(self) -> None:  # noqa: C901 - state machine is inherently branchy
        device_id = self.device.id
        start_time = time.monotonic()

        try:
            self.status_changed.emit(device_id, STATUS_PREPARING)
            self.log_line.emit(device_id, f">>> Preparing to flash '{self.device.name}' on {self.device.com_port}")

            command = FlashCommandBuilder.build_write_flash_args(self.device)
            self.log_line.emit(device_id, ">>> Command: " + " ".join(command))

            if self._cancel_requested:
                self._finish(device_id, False, "Cancelled before start.", start_time)
                return

            self._process = FlashProcess(command)
            self._process.start()

            self.status_changed.emit(device_id, STATUS_CONNECTING)

            port_lost = False
            wrote_any = False
            stalled = False
            fatal_detail = ""
            for line in self._process.iter_lines(stall_timeout=FLASH_STALL_TIMEOUT_SECONDS):
                if self._cancel_requested:
                    break

                if line is None:
                    # No output at all for FLASH_STALL_TIMEOUT_SECONDS: the
                    # subprocess is treated as hung (typically the device
                    # dropped off the bus mid-write and the OS driver never
                    # unblocked esptool's write/read call), not merely slow.
                    # Killing it here is what stops the status badge -- and
                    # anything else keyed off is_busy(), like the Serial
                    # Monitor's busy-port check -- from being stuck on
                    # "Uploading" until the whole app is restarted.
                    stalled = True
                    self.log_line.emit(
                        device_id,
                        f">>> No response for {int(FLASH_STALL_TIMEOUT_SECONDS)}s -- "
                        "the device appears to have disconnected. Aborting.",
                    )
                    break

                self.log_line.emit(device_id, line)
                event = parse_progress_line(line)

                if event.kind == "erasing":
                    self.status_changed.emit(device_id, STATUS_ERASING)
                elif event.kind == "writing":
                    # Re-emit STATUS_UPLOADING on every "Writing at..." line,
                    # not just the first one. A project with more than one
                    # firmware entry gets a "Hash of data verified." line
                    # (-> STATUS_VERIFYING) after EACH file, followed by the
                    # next file's "Writing at..." line. Only firing this
                    # once left the status badge stuck on "Verifying" for
                    # the rest of the run even though esptool had already
                    # moved on to writing the next segment.
                    self.status_changed.emit(device_id, STATUS_UPLOADING)
                    wrote_any = True
                    if event.percent is not None:
                        self.progress_changed.emit(device_id, event.percent, event.address)
                        self._update_speed(device_id, start_time)
                elif event.kind == "verifying":
                    self.status_changed.emit(device_id, STATUS_VERIFYING)
                elif event.kind == "fatal_error":
                    # esptool's own "A fatal error occurred: ..." summary --
                    # this is an EXPECTED failure mode (bad cable, board not
                    # in bootloader mode, no serial data received, etc.),
                    # not a bug in this app. Its message text is kept so
                    # the eventual _finish() call surfaces exactly what
                    # esptool itself said, instead of just an exit code.
                    fatal_detail = event.detail
                elif event.kind == "port_lost":
                    # The board isn't reachable on the selected port -- either
                    # it was never there (wrong port / not plugged in yet, in
                    # the rare case that slipped past the pre-upload port
                    # check) or it dropped off the bus mid-flash (loose
                    # cable, brown-out, driver hiccup). esptool itself will
                    # retry a few times and then raise, which prints a Python
                    # traceback into this same stream -- remembered here so
                    # the final failure message is a clear, actionable
                    # sentence instead of a bare "exited with code 1".
                    port_lost = True

            if stalled:
                self._process.terminate()
                self._finish(
                    device_id, False,
                    f"Device stopped responding on {self.device.com_port} for "
                    f"over {int(FLASH_STALL_TIMEOUT_SECONDS)}s during flashing (likely "
                    "disconnected). Check the USB cable/connection and retry.",
                    start_time,
                )
                return

            if self._cancel_requested:
                self._process.terminate()
                self._finish(device_id, False, "Cancelled by user.", start_time)
                return

            return_code = self._process.wait(timeout=10)

            if return_code == 0:
                self.progress_changed.emit(device_id, 100, "")
                self._finish(device_id, True, "Flash completed successfully.", start_time)
            elif port_lost and wrote_any:
                self._finish(
                    device_id, False,
                    f"Device disconnected from {self.device.com_port} during flashing "
                    "(the port became unavailable). Check the USB cable/connection and retry.",
                    start_time,
                )
            elif port_lost:
                # Prefer esptool's own "A fatal error occurred: ..." text
                # when we have it (e.g. "No serial data received.") -- it's
                # usually more specific than this app's generic wording.
                if fatal_detail:
                    message = (
                        f"Could not connect to {self.device.com_port}: {fatal_detail} Check the "
                        "cable/connection, that the board is in bootloader mode, and that the "
                        "correct port is selected, then retry."
                    )
                else:
                    message = (
                        f"Could not connect to {self.device.com_port} (port unavailable or already "
                        "in use). Check the cable/connection, that the correct port is selected, "
                        "and that no other program has it open, then retry."
                    )
                self._finish(device_id, False, message, start_time)
            elif fatal_detail:
                self._finish(device_id, False, fatal_detail, start_time)
            else:
                self._finish(device_id, False, f"esptool exited with code {return_code}.", start_time)

        except FileNotFoundError as exc:
            logger.exception("esptool executable/module not found for device %s", self.device.name)
            self.log_line.emit(device_id, f"ERROR: {exc}")
            self._finish(device_id, False, "esptool could not be launched (is it installed?).", start_time)
        except Exception as exc:  # noqa: BLE001 - worker must never crash the app
            logger.exception("Unexpected error flashing device %s", self.device.name)
            self.log_line.emit(device_id, f"ERROR: {exc}")
            self._finish(device_id, False, f"Unexpected error: {exc}", start_time)

    # ------------------------------------------------------------------
    def _update_speed(self, device_id: str, start_time: float) -> None:
        """Rough throughput estimate for the UI's 'transfer speed' column."""
        elapsed = max(time.monotonic() - start_time, 0.001)
        enabled = self.device.enabled_firmware()
        total_bytes = sum(e.file_size for e in enabled)
        if total_bytes <= 0:
            return
        kbps = (total_bytes / elapsed) / 1024.0
        self.speed_changed.emit(device_id, kbps)

    def _finish(self, device_id: str, success: bool, message: str, start_time: float) -> None:
        duration = time.monotonic() - start_time
        status = STATUS_COMPLETED if success else (
            STATUS_CANCELLED if self._cancel_requested else STATUS_FAILED
        )
        self.status_changed.emit(device_id, status)
        self.log_line.emit(device_id, f">>> {message} (elapsed {duration:.1f}s)")
        self.finished_flash.emit(device_id, success, message, duration)
