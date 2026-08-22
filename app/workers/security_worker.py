"""
security_worker.py
===================
ProvisionWorker runs entirely inside its own QThread and drives the full
"provision this device" sequence: generate any keys the user asked to
generate (offline), then burn the requested eFuse blocks (online, via
`espefuse`, talking to real hardware) -- one worker instance per device,
mirroring FlashWorker's shape so the same live-console/status-badge UI
patterns apply.

This module never performs cryptography or eFuse protocol work itself; it
only sequences calls into app/flash_engine/security_manager.py, which in
turn only builds `espsecure`/`espefuse` command lines.

Every eFuse-burning step here is expected to have already passed through
this app's own explicit, typed-confirmation dialog (see
app/ui/provision_confirm_dialog.py) before this worker is ever started --
this class does not re-confirm, it only executes what's already been
approved.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from app.flash_engine.esptool_wrapper import FlashProcess
from app.flash_engine.security_manager import (
    SecurityCommandBuilder,
    generate_flash_encryption_key,
    generate_signing_key,
)
from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.constants import (
    STATUS_BURNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_GENERATING_KEY,
)

logger = get_logger(__name__)


class ProvisionWorker(QThread):
    """
    Signals
    -------
    status_changed(device_id, status_str)
    log_line(device_id, line_str)
    finished_provision(device_id, success_bool, message_str, duration_seconds)
    """

    status_changed = Signal(str, str)
    log_line = Signal(str, str)
    finished_provision = Signal(str, bool, str, float)

    def __init__(self, device: DeviceConfig, parent=None) -> None:
        super().__init__(parent)
        self.device = device
        self._process: FlashProcess | None = None
        self._cancel_requested = False

    # ------------------------------------------------------------------
    def request_cancel(self) -> None:
        self._cancel_requested = True
        if self._process is not None:
            self._process.terminate()

    # ------------------------------------------------------------------
    def run(self) -> None:  # noqa: C901 - sequential provisioning steps are inherently branchy
        device_id = self.device.id
        start_time = time.monotonic()
        sec = self.device.security

        try:
            # ---- Step 1: key generation (offline, fast) ----
            if sec.enable_flash_encryption and sec.key_source == "generate":
                self.status_changed.emit(device_id, STATUS_GENERATING_KEY)
                self.log_line.emit(device_id, ">>> Generating flash encryption key...")
                result = generate_flash_encryption_key(sec.flash_encryption_key_path)
                self._log_multiline(device_id, result.output_text)
                if not result.success:
                    self._finish(device_id, False, f"Key generation failed: {result.error_message}", start_time)
                    return
                self.log_line.emit(device_id, f">>> Key written to {sec.flash_encryption_key_path}")

            if sec.enable_secure_boot and sec.key_source == "generate":
                self.status_changed.emit(device_id, STATUS_GENERATING_KEY)
                self.log_line.emit(device_id, ">>> Generating secure boot signing key...")
                result = generate_signing_key(
                    sec.secure_boot_key_path, sec.secure_boot_version, sec.secure_boot_scheme,
                )
                self._log_multiline(device_id, result.output_text)
                if not result.success:
                    self._finish(device_id, False, f"Signing key generation failed: {result.error_message}", start_time)
                    return
                self.log_line.emit(device_id, f">>> Key written to {sec.secure_boot_key_path}")

            if self._cancel_requested:
                self._finish(device_id, False, "Cancelled before burning any eFuses.", start_time)
                return

            # ---- Step 2: burn eFuses (online, irreversible) ----
            if sec.enable_flash_encryption:
                self.status_changed.emit(device_id, STATUS_BURNING)
                self.log_line.emit(device_id, ">>> Burning flash encryption key to eFuse...")
                command = SecurityCommandBuilder.build_burn_flash_encryption_key_args(self.device)
                if not self._run_subprocess(device_id, command):
                    self._finish(device_id, False, "Burning the flash encryption key failed. See log above.", start_time)
                    return

            if self._cancel_requested:
                self._finish(device_id, False, "Cancelled after flash encryption key burn.", start_time)
                return

            if sec.enable_secure_boot:
                self.status_changed.emit(device_id, STATUS_BURNING)
                self.log_line.emit(device_id, ">>> Burning secure boot key digest to eFuse...")
                command = SecurityCommandBuilder.build_burn_secure_boot_key_args(self.device)
                if not self._run_subprocess(device_id, command):
                    self._finish(device_id, False, "Burning the secure boot key digest failed. See log above.", start_time)
                    return

            self._finish(device_id, True, "Provisioning completed successfully.", start_time)

        except FileNotFoundError as exc:
            logger.exception("espsecure/espefuse executable/module not found for device %s", self.device.name)
            self.log_line.emit(device_id, f"ERROR: {exc}")
            self._finish(device_id, False, "espsecure/espefuse could not be launched (is esptool installed?).", start_time)
        except Exception as exc:  # noqa: BLE001 - worker must never crash the app
            logger.exception("Unexpected error provisioning device %s", self.device.name)
            self.log_line.emit(device_id, f"ERROR: {exc}")
            self._finish(device_id, False, f"Unexpected error: {exc}", start_time)

    # ------------------------------------------------------------------
    def _run_subprocess(self, device_id: str, command: list[str]) -> bool:
        """Run one espefuse subprocess to completion, streaming its output
        into the live log. Returns True on a clean (exit code 0) finish."""
        self.log_line.emit(device_id, ">>> Command: " + " ".join(command))
        self._process = FlashProcess(command)
        self._process.start()
        for line in self._process.iter_lines(stall_timeout=60.0):
            if self._cancel_requested:
                self._process.terminate()
                return False
            if line is None:
                self.log_line.emit(device_id, ">>> No response for 60s -- aborting.")
                self._process.terminate()
                return False
            self.log_line.emit(device_id, line)
        return_code = self._process.wait(timeout=10)
        return return_code == 0

    def _log_multiline(self, device_id: str, text: str) -> None:
        for line in text.splitlines():
            if line.strip():
                self.log_line.emit(device_id, line)

    def _finish(self, device_id: str, success: bool, message: str, start_time: float) -> None:
        duration = time.monotonic() - start_time
        status = STATUS_COMPLETED if success else STATUS_FAILED
        self.status_changed.emit(device_id, status)
        self.log_line.emit(device_id, f">>> {message} (elapsed {duration:.1f}s)")
        self.finished_provision.emit(device_id, success, message, duration)
