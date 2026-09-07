"""
merge_worker.py
================
Reliability fix: bin_merge.run_merge() used to run `esptool merge-bin`
synchronously via `subprocess.run` directly on the GUI thread, with no
cancel button and no progress feedback beyond a busy-cursor convention --
a large or slow merge froze the whole application for up to its
MERGE_TIMEOUT_SECONDS (180s) timeout.

MergeWorker moves that same esptool invocation onto a QThread, reusing
FlashProcess (app/flash_engine/esptool_wrapper.py) -- the same
Popen-plus-background-reader-thread wrapper FlashWorker already uses for
parallel device flashing -- so output streams line-by-line, a Cancel
button can actually stop the subprocess, and the GUI stays responsive.

bin_merge.run_merge() itself is left untouched (still synchronous) for any
non-GUI caller and for its existing test suite (tests/firmware_manager/
test_bin_merge.py); MergeWorker is the GUI-facing path, used exclusively
by app/ui/merge_bin_dialog.py.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.firmware_manager.bin_merge import MERGE_TIMEOUT_SECONDS, MergeResult
from app.flash_engine.esptool_wrapper import FlashCommandBuilder, FlashProcess
from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.utilities.helpers import propagate_trace_hook

logger = get_logger(__name__)

# How often iter_lines() is polled for a stalled/silent subprocess while
# still letting us notice a cancel request or overall timeout promptly.
_POLL_INTERVAL_SECONDS = 0.5


class MergeWorker(QThread):
    """
    Signals
    -------
    log_line(str)              - one line of esptool merge-bin output
    merge_finished(object)     - MergeResult, emitted exactly once
    """

    log_line = Signal(str)
    merge_finished = Signal(object)

    def __init__(
        self,
        entries: list[FirmwareEntry],
        chip: str,
        output_path: str,
        flash_mode: str = "keep",
        flash_frequency: str = "keep",
        flash_size: str = "keep",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._entries = entries
        self._chip = chip
        self._output_path = output_path
        self._flash_mode = flash_mode
        self._flash_frequency = flash_frequency
        self._flash_size = flash_size
        self._process: FlashProcess | None = None
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Thread-safe-ish cancel request; polled by _run_impl() and also
        used to actively kill the running subprocess for immediate
        response (mirrors FlashWorker.request_cancel)."""
        self._cancel_requested = True
        if self._process is not None:
            self._process.terminate()

    # ------------------------------------------------------------------
    def run(self) -> None:
        # QThread bypasses Python's threading module, so coverage's tracer
        # never auto-attaches to this thread; re-arm it before delegating
        # to the real implementation. See helpers.propagate_trace_hook.
        propagate_trace_hook()
        self._run_impl()

    def _run_impl(self) -> None:
        address_file_pairs = [(entry.address, entry.file_path) for entry in self._entries]
        command = FlashCommandBuilder.build_merge_bin_args(
            chip=self._chip,
            entries=address_file_pairs,
            output_path=self._output_path,
            flash_mode=self._flash_mode,
            flash_frequency=self._flash_frequency,
            flash_size=self._flash_size,
        )
        logger.info("Running bin merge (background thread): %s", " ".join(command))
        self.log_line.emit(">>> " + " ".join(command))

        if self._cancel_requested:
            self._finish(self._cancelled_result(command, ""))
            return

        try:
            self._process = FlashProcess(command)
            self._process.start()
        except FileNotFoundError as exc:
            logger.exception("esptool executable/module not found while merging")
            self._finish(MergeResult(
                success=False, output_path=self._output_path, command=command, output_text="",
                error_message=f"esptool could not be launched (is it installed?): {exc}",
            ))
            return
        except Exception as exc:  # noqa: BLE001 - worker must never crash the app
            logger.exception("Unexpected error starting bin merge")
            self._finish(MergeResult(
                success=False, output_path=self._output_path, command=command, output_text="",
                error_message=f"Unexpected error: {exc}",
            ))
            return

        output_lines: list[str] = []
        start_time = time.monotonic()
        timed_out = False
        try:
            for line in self._process.iter_lines(stall_timeout=_POLL_INTERVAL_SECONDS):
                if self._cancel_requested:
                    break
                if line is None:
                    if time.monotonic() - start_time > MERGE_TIMEOUT_SECONDS:
                        timed_out = True
                        break
                    continue
                output_lines.append(line)
                self.log_line.emit(line)
        except Exception as exc:  # noqa: BLE001 - worker must never crash the app
            logger.exception("Unexpected error while merging bins")
            self._process.terminate()
            self._finish(MergeResult(
                success=False, output_path=self._output_path, command=command,
                output_text="\n".join(output_lines), error_message=f"Unexpected error: {exc}",
            ))
            return

        output_text = "\n".join(output_lines)

        if self._cancel_requested:
            self._process.terminate()
            self._finish(self._cancelled_result(command, output_text))
            return

        if timed_out:
            self._process.terminate()
            self._finish(MergeResult(
                success=False, output_path=self._output_path, command=command,
                output_text=output_text,
                error_message=f"Merge timed out after {MERGE_TIMEOUT_SECONDS}s.",
            ))
            return

        return_code = self._process.wait(timeout=10)
        if return_code == 0 and Path(self._output_path).is_file():
            self._finish(MergeResult(
                success=True, output_path=self._output_path, command=command, output_text=output_text,
            ))
            return

        self._finish(MergeResult(
            success=False, output_path=self._output_path, command=command,
            output_text=output_text,
            error_message=f"esptool merge-bin exited with code {return_code}.",
        ))

    def _cancelled_result(self, command: list[str], output_text: str) -> MergeResult:
        return MergeResult(
            success=False, output_path=self._output_path, command=command,
            output_text=output_text, error_message="Merge cancelled by user.",
        )

    def _finish(self, result: MergeResult) -> None:
        self.merge_finished.emit(result)
