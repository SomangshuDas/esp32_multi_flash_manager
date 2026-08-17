"""
esptool_wrapper.py
===================
The single point of contact with the official `esptool` package.

Design decision: esptool is invoked as an OUT-OF-PROCESS subprocess
(``python -m esptool ...``) rather than calling ``esptool.main()``
in-process. Reasons:

  1. esptool writes progress using carriage-return ("\\r") updates and
     calls sys.exit() internally on failure — none of that plays nicely
     with a Qt GUI thread or with running many devices in parallel.
  2. A crashed/hung esptool subprocess can be killed cleanly (Cancel
     button) without taking down the whole application.
  3. Raw, unmodified esptool console output can be shown verbatim in the
     "Live Output" console, which is an explicit requirement.

FlashCommandBuilder turns a DeviceConfig into the exact esptool argument
list. FlashProcess wraps subprocess.Popen and exposes a line-by-line
iterator plus a parser that extracts structured progress events from
esptool's stdout.
"""

from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Iterator

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.constants import ESPTOOL_REEXEC_FLAG

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Regexes used to turn raw esptool stdout lines into structured progress.
#
# esptool's own progress-line format has changed across major versions, and
# both are seen in the wild depending on which esptool build a machine has:
#
#   legacy (esptool < 5):
#     "Writing at 0x00010000... (42 %)"
#   current (esptool 5.x, rich-based progress bar, plain-text when piped):
#     "Writing at 0x00001000 [ ] 0.0% 0/13104 bytes..."
#     "Writing at 0x00005a30 [==============================] 100.0% 13104/13104 bytes..."
#
# The legacy-only pattern silently matched nothing against 5.x output,
# which meant every "writing" line fell through to "raw" -- no progress
# updates, and no re-assertion of the "Uploading" status after a prior
# "Hash of data verified." line, leaving the status badge stuck on
# "Verifying" for the rest of the run even though esptool was actively
# writing the next file. Both formats are matched here so this keeps
# working regardless of which esptool version is bundled/installed.
# --------------------------------------------------------------------------
_RE_WRITING_AT_LEGACY = re.compile(r"Writing at (0x[0-9a-fA-F]+)\.\.\.\s*\((\d+(?:\.\d+)?)\s*%\)")
_RE_WRITING_AT_CURRENT = re.compile(r"Writing at (0x[0-9a-fA-F]+)\s*\[[^\]]*\]\s*(\d+(?:\.\d+)?)\s*%")
_RE_CONNECTING = re.compile(r"Connecting\.\.\.|Serial port")
_RE_ERASING = re.compile(r"Erasing flash|Chip erase")
_RE_HASH_VERIFIED = re.compile(r"Hash of data verified")
_RE_HARD_RESET = re.compile(r"Hard resetting|Leaving\.\.\.")
_RE_PORT_LOST = re.compile(r"could not open port|port is busy or doesn't exist", re.IGNORECASE)


@dataclass
class ProgressEvent:
    kind: str  # "connecting" | "erasing" | "writing" | "verifying" | "resetting" | "port_lost" | "raw"
    address: str = ""
    percent: int | None = None
    raw_line: str = ""


def parse_progress_line(line: str) -> ProgressEvent:
    """Turn a single line of esptool stdout into a structured ProgressEvent."""
    match = _RE_WRITING_AT_CURRENT.search(line) or _RE_WRITING_AT_LEGACY.search(line)
    if match:
        percent = int(round(float(match.group(2))))
        return ProgressEvent(kind="writing", address=match.group(1), percent=percent, raw_line=line)
    if _RE_ERASING.search(line):
        return ProgressEvent(kind="erasing", raw_line=line)
    if _RE_HASH_VERIFIED.search(line):
        return ProgressEvent(kind="verifying", raw_line=line)
    if _RE_PORT_LOST.search(line):
        return ProgressEvent(kind="port_lost", raw_line=line)
    if _RE_CONNECTING.search(line):
        return ProgressEvent(kind="connecting", raw_line=line)
    if _RE_HARD_RESET.search(line):
        return ProgressEvent(kind="resetting", raw_line=line)
    return ProgressEvent(kind="raw", raw_line=line)


def _esptool_command_prefix() -> list[str]:
    """
    Base argv used to launch esptool as a subprocess.

    Running from source: `sys.executable` is a real Python interpreter, so
    `-m esptool` works exactly as expected.

    Running as a frozen PyInstaller build: `sys.executable` is this app's
    OWN .exe, not a Python interpreter -- there is nothing on the target
    machine to run `-m esptool` with. esptool is instead bundled directly
    into the exe, so we re-invoke this same exe with a hidden internal flag
    that main.py intercepts to run esptool's CLI in-process and exit,
    rather than launching a second copy of the GUI (which is what silently
    happened before this fix: Upload would open a second blank app window
    instead of ever actually flashing).
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, ESPTOOL_REEXEC_FLAG]
    return [sys.executable, "-m", "esptool"]


class FlashCommandBuilder:
    """Builds the exact `esptool` CLI argument list for a given device."""

    @staticmethod
    def build_write_flash_args(device: DeviceConfig) -> list[str]:
        """
        Build the full command line (as a list, suitable for subprocess.Popen)
        to flash every ENABLED firmware entry on `device`.
        """
        args: list[str] = _esptool_command_prefix()

        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]

        args += ["--port", device.com_port]
        args += ["--baud", str(device.baud_rate)]

        if not device.stub_loader:
            args += ["--no-stub"]

        args += ["write-flash"]

        if device.flash_mode and device.flash_mode != "keep":
            args += ["--flash-mode", device.flash_mode]
        if device.flash_frequency and device.flash_frequency != "keep":
            args += ["--flash-freq", device.flash_frequency]
        if device.flash_size and device.flash_size != "keep":
            args += ["--flash-size", device.flash_size]

        if device.erase_before_upload:
            args += ["--erase-all"]

        if not device.compression:
            args += ["--no-compress"]

        if not device.reset_after_upload:
            args += ["--after", "no-reset"]

        if device.custom_flash_args.strip():
            # Allow power users to append raw extra arguments (e.g. --no-progress)
            args += device.custom_flash_args.strip().split()

        for entry in device.enabled_firmware():
            args += [entry.address, entry.file_path]

        return args

    @staticmethod
    def build_erase_flash_args(device: DeviceConfig) -> list[str]:
        """Build a command line to fully erase the chip's flash (no writing)."""
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "erase-flash"]
        return args

    @staticmethod
    def build_chip_id_args(device: DeviceConfig) -> list[str]:
        """Build a lightweight command used to probe/identify a connected chip."""
        args: list[str] = _esptool_command_prefix()
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "chip-id"]
        return args


class FlashProcess:
    """
    Thin wrapper around subprocess.Popen for running an esptool command and
    streaming its stdout line-by-line. Used from within FlashWorker
    (a QThread), never from the GUI thread directly.
    """

    def __init__(self, command: list[str]) -> None:
        self.command = command
        self._process: subprocess.Popen | None = None
        self._line_queue: "queue.Queue[str | None]" = queue.Queue()
        self._reader_thread: threading.Thread | None = None

    def start(self) -> None:
        logger.debug("Launching esptool subprocess: %s", " ".join(self.command))
        creationflags = 0
        if sys.platform == "win32":
            # Prevent a flashing console window from popping up per device.
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._process = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=creationflags,
        )
        # stdout is drained on a dedicated daemon thread into a queue rather
        # than iterated directly, so the caller can poll with a timeout (see
        # iter_lines) instead of blocking forever. This matters because a
        # device that disconnects mid-write can leave the OS serial driver
        # parked in an uninterruptible I/O wait that esptool has no timeout
        # for -- without this, a plain `for line in process.stdout` never
        # returns, and the FlashWorker QThread reading it never finishes.
        self._reader_thread = threading.Thread(target=self._drain_stdout, daemon=True)
        self._reader_thread.start()

    def _drain_stdout(self) -> None:
        if self._process is not None and self._process.stdout is not None:
            for raw_line in self._process.stdout:
                line = raw_line.rstrip("\r\n")
                if line:
                    self._line_queue.put(line)
        self._line_queue.put(None)  # sentinel: stdout closed / process exited

    def iter_lines(self, stall_timeout: float | None = None) -> Iterator[str | None]:
        """
        Yield decoded stdout lines as they arrive, until the process exits.

        If `stall_timeout` is given (seconds) and no line -- nor the
        end-of-stream sentinel -- arrives within that window, yields `None`
        once per timeout window instead of blocking forever. Callers use a
        `None` to detect a genuinely unresponsive/hung subprocess and abort,
        rather than leaving the worker parked indefinitely (see start()).
        """
        if self._process is None:
            return
        while True:
            try:
                line = self._line_queue.get(timeout=stall_timeout)
            except queue.Empty:
                yield None
                continue
            if line is None:
                return
            yield line

    def wait(self, timeout: float | None = None) -> int:
        if self._process is None:
            return -1
        return self._process.wait(timeout=timeout)

    @property
    def return_code(self) -> int | None:
        if self._process is None:
            return None
        return self._process.poll()

    def terminate(self) -> None:
        """Attempt a graceful terminate, escalating to kill if needed."""
        if self._process is None or self._process.poll() is not None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logger.warning("esptool subprocess did not terminate gracefully; killing")
            self._process.kill()
        except Exception:  # noqa: BLE001
            logger.exception("Error while terminating esptool subprocess")
