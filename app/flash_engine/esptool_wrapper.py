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

import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterator

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Regexes used to turn raw esptool stdout lines into structured progress.
# esptool prints lines such as:
#   "Writing at 0x00010000... (42 %)"
#   "Wrote 1048576 bytes (612345 compressed) at 0x00010000 in 8.4 seconds..."
#   "Hash of data verified."
# --------------------------------------------------------------------------
_RE_WRITING_AT = re.compile(r"Writing at (0x[0-9a-fA-F]+)\.\.\.\s*\((\d+)\s*%\)")
_RE_WROTE = re.compile(
    r"Wrote (\d+) bytes.*at (0x[0-9a-fA-F]+) in ([\d.]+) seconds"
)
_RE_CONNECTING = re.compile(r"Connecting\.\.\.|Serial port")
_RE_ERASING = re.compile(r"Erasing flash|Chip erase")
_RE_HASH_VERIFIED = re.compile(r"Hash of data verified")
_RE_HARD_RESET = re.compile(r"Hard resetting|Leaving\.\.\.")


@dataclass
class ProgressEvent:
    kind: str  # "connecting" | "erasing" | "writing" | "verifying" | "resetting" | "raw"
    address: str = ""
    percent: int | None = None
    raw_line: str = ""


def parse_progress_line(line: str) -> ProgressEvent:
    """Turn a single line of esptool stdout into a structured ProgressEvent."""
    match = _RE_WRITING_AT.search(line)
    if match:
        return ProgressEvent(kind="writing", address=match.group(1), percent=int(match.group(2)), raw_line=line)
    if _RE_ERASING.search(line):
        return ProgressEvent(kind="erasing", raw_line=line)
    if _RE_HASH_VERIFIED.search(line):
        return ProgressEvent(kind="verifying", raw_line=line)
    if _RE_CONNECTING.search(line):
        return ProgressEvent(kind="connecting", raw_line=line)
    if _RE_HARD_RESET.search(line):
        return ProgressEvent(kind="resetting", raw_line=line)
    return ProgressEvent(kind="raw", raw_line=line)


class FlashCommandBuilder:
    """Builds the exact `esptool` CLI argument list for a given device."""

    @staticmethod
    def build_write_flash_args(device: DeviceConfig) -> list[str]:
        """
        Build the full command line (as a list, suitable for subprocess.Popen)
        to flash every ENABLED firmware entry on `device`.
        """
        args: list[str] = [sys.executable, "-m", "esptool"]

        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]

        args += ["--port", device.com_port]
        args += ["--baud", str(device.baud_rate)]

        if not device.stub_loader:
            args += ["--no-stub"]

        args += ["write_flash"]

        if device.flash_mode and device.flash_mode != "keep":
            args += ["--flash_mode", device.flash_mode]
        if device.flash_frequency and device.flash_frequency != "keep":
            args += ["--flash_freq", device.flash_frequency]
        if device.flash_size and device.flash_size != "keep":
            args += ["--flash_size", device.flash_size]

        if device.erase_before_upload:
            args += ["--erase-all"]

        if device.verify_flash:
            args += ["--verify"]

        if not device.compression:
            args += ["--no-compress"]

        if not device.reset_after_upload:
            args += ["--after", "no_reset"]

        if device.custom_flash_args.strip():
            # Allow power users to append raw extra arguments (e.g. --no-progress)
            args += device.custom_flash_args.strip().split()

        for entry in device.enabled_firmware():
            args += [entry.address, entry.file_path]

        return args

    @staticmethod
    def build_erase_flash_args(device: DeviceConfig) -> list[str]:
        """Build a command line to fully erase the chip's flash (no writing)."""
        args: list[str] = [sys.executable, "-m", "esptool"]
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "erase_flash"]
        return args

    @staticmethod
    def build_chip_id_args(device: DeviceConfig) -> list[str]:
        """Build a lightweight command used to probe/identify a connected chip."""
        args: list[str] = [sys.executable, "-m", "esptool"]
        if device.chip_type and device.chip_type != "auto":
            args += ["--chip", device.chip_type]
        args += ["--port", device.com_port, "--baud", str(device.baud_rate), "chip_id"]
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

    def iter_lines(self) -> Iterator[str]:
        """Yield decoded stdout lines as they arrive, until the process exits."""
        if self._process is None or self._process.stdout is None:
            return
        for raw_line in self._process.stdout:
            line = raw_line.rstrip("\r\n")
            if line:
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
