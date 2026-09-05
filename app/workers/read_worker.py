"""
read_worker.py
===============
ReadWorker runs entirely inside its own QThread and drives a single
read-only inspection operation for one device: Chip Info, Flash ID, eFuse
Summary, Security Info, or a raw Read Flash Region -- the equivalent of
Espressif's Flash Download Tool's own "read back" panel, built entirely on
`esptool`'s and `espefuse`'s own read-only commands (chip-id, flash-id,
get-security-info, read-flash, and espefuse's summary/dump). Nothing here
writes to eFuse or flash; every command this module can run is read-only
on real hardware.

Kept independent of FlashWorker/ProvisionWorker (own QThread, own
signals) since it's used from a separate, always-available "Read Flash /
eFuse / Chip Info..." dialog rather than the main upload workflow, and can
run at any time a device isn't mid-flash.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from app.flash_engine.esptool_wrapper import FlashCommandBuilder, FlashProcess
from app.flash_engine.security_manager import SecurityCommandBuilder
from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.app_settings import get_flash_stall_timeout_seconds
from app.utilities.constants import (
    READ_MODE_CHIP_INFO,
    READ_MODE_EFUSE_SUMMARY,
    READ_MODE_FLASH_ID,
    READ_MODE_READ_FLASH,
    READ_MODE_SECURITY_INFO,
)
from app.utilities.helpers import propagate_trace_hook

logger = get_logger(__name__)


def build_read_command(
    device: DeviceConfig,
    mode: str,
    *,
    read_address: str = "",
    read_size: str = "",
    output_path: str = "",
) -> list[str]:
    """Resolve `mode` (one of the READ_MODE_* constants) into the exact
    esptool/espefuse command line to run. Kept as a free function so the
    Read dialog can preview the command before running it."""
    if mode == READ_MODE_CHIP_INFO:
        return FlashCommandBuilder.build_chip_id_args(device)
    if mode == READ_MODE_FLASH_ID:
        return FlashCommandBuilder.build_flash_id_args(device)
    if mode == READ_MODE_SECURITY_INFO:
        return FlashCommandBuilder.build_security_info_args(device)
    if mode == READ_MODE_EFUSE_SUMMARY:
        return SecurityCommandBuilder.build_efuse_summary_args(device, output_path)
    if mode == READ_MODE_READ_FLASH:
        return FlashCommandBuilder.build_read_flash_args(device, read_address, read_size, output_path)
    raise ValueError(f"Unknown read mode: {mode}")


class ReadWorker(QThread):
    """
    Signals
    -------
    log_line(line_str)
    finished_read(success_bool, message_str, output_path_str)
    """

    log_line = Signal(str)
    finished_read = Signal(bool, str, str)

    def __init__(
        self,
        device: DeviceConfig,
        mode: str,
        read_address: str = "",
        read_size: str = "",
        output_path: str = "",
        parent=None,
        *,
        stall_timeout: float | None = None,
    ) -> None:
        super().__init__(parent)
        self.device = device
        self.mode = mode
        self.read_address = read_address
        self.read_size = read_size
        self.output_path = output_path
        self._process: FlashProcess | None = None
        self._cancel_requested = False
        # Resolved on the MAIN thread if not given explicitly -- never
        # read from inside run()/_run_impl() itself. See the matching
        # comment on FlashWorker.__init__ in flash_worker.py for why:
        # this app's settings loader touches os.environ the first time
        # it's ever called in the process, and doing that from a
        # background QThread at the same moment the main thread mutates
        # env vars (as this app's own test suite does between tests) can
        # abort the whole process.
        self._stall_timeout = (
            stall_timeout if stall_timeout is not None else get_flash_stall_timeout_seconds()
        )

    def request_cancel(self) -> None:
        self._cancel_requested = True
        if self._process is not None:
            self._process.terminate()

    def run(self) -> None:
        # See helpers.propagate_trace_hook: QThread bypasses threading, so
        # coverage's tracer never auto-attaches without this.
        propagate_trace_hook()
        self._run_impl()

    def _run_impl(self) -> None:
        start_time = time.monotonic()
        stall_timeout = self._stall_timeout
        try:
            command = build_read_command(
                self.device, self.mode,
                read_address=self.read_address, read_size=self.read_size,
                output_path=self.output_path,
            )
        except ValueError as exc:
            self.finished_read.emit(False, str(exc), "")
            return

        self.log_line.emit(">>> Command: " + " ".join(command))

        try:
            self._process = FlashProcess(command)
            self._process.start()
        except FileNotFoundError as exc:
            logger.exception("esptool/espefuse executable/module not found for read operation")
            self.finished_read.emit(False, f"Could not launch esptool/espefuse: {exc}", "")
            return
        except Exception as exc:  # noqa: BLE001 - worker must never crash the app
            logger.exception("Unexpected error starting read operation")
            self.finished_read.emit(False, f"Unexpected error: {exc}", "")
            return

        for line in self._process.iter_lines(stall_timeout=stall_timeout):
            if self._cancel_requested:
                self._process.terminate()
                self.finished_read.emit(False, "Cancelled by user.", self.output_path)
                return
            if line is None:
                self.log_line.emit(f">>> No response for {int(stall_timeout)}s -- the device appears unresponsive. Aborting.")
                self._process.terminate()
                self.finished_read.emit(
                    False,
                    f"Device stopped responding on {self.device.com_port}. Check the connection and retry.",
                    self.output_path,
                )
                return
            self.log_line.emit(line)

        return_code = self._process.wait(timeout=10)
        duration = time.monotonic() - start_time
        if return_code == 0:
            self.finished_read.emit(True, f"Completed successfully ({duration:.1f}s).", self.output_path)
        else:
            self.finished_read.emit(False, f"Exited with code {return_code}.", self.output_path)
