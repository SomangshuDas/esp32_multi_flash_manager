"""
Mocked-subprocess tests for app/workers/merge_worker.py.

Mirrors the approach in tests/workers/test_flash_worker_e2e.py: drives the
REAL production code (MergeWorker.run(), its QThread lifecycle,
FlashController-style cancel handling) but replaces FlashProcess -- the
one class that actually launches a subprocess -- with a fake that plays
back scripted stdout lines. No real esptool binary is touched.
"""

from __future__ import annotations

import threading

import pytest

from app.firmware_manager.bin_merge import MERGE_TIMEOUT_SECONDS
from app.models.firmware_model import FirmwareEntry
from app.workers import merge_worker as merge_worker_module
from app.workers.merge_worker import MergeWorker


def make_fake_process(lines, return_code=0, block_after: int | None = None):
    """Same shape as test_flash_worker_e2e.make_fake_flash_process: plays
    back `lines` through iter_lines(), then reports `return_code` from
    wait(). If `block_after` is given, iter_lines() blocks after yielding
    that many lines until terminate() is called."""

    class FakeProcess:
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

    return FakeProcess


@pytest.fixture
def entries(tmp_path):
    fw_path = tmp_path / "firmware.bin"
    fw_path.write_bytes(b"\x00" * 16)
    entry = FirmwareEntry(file_path=str(fw_path), address="0x10000")
    entry.refresh()
    return [entry]


SUCCESSFUL_LINES = [
    "esptool.py v5.0.0",
    "Merged binary written to output.bin",
]


class TestSuccess:
    def test_success_writes_result_and_emits_log_lines(self, qtbot, monkeypatch, tmp_path, entries):
        output_path = tmp_path / "merged.bin"
        output_path.write_bytes(b"\x00")  # stand-in for esptool having written it

        monkeypatch.setattr(
            merge_worker_module, "FlashProcess",
            make_fake_process(SUCCESSFUL_LINES, return_code=0),
        )
        worker = MergeWorker(entries, "esp32", str(output_path))
        seen_lines: list[str] = []
        worker.log_line.connect(seen_lines.append)

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.start()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is True
        assert result.output_path == str(output_path)
        assert any("Merged binary" in line for line in seen_lines)

    def test_missing_output_file_after_success_return_code_is_still_a_failure(self, qtbot, monkeypatch, tmp_path, entries):
        # esptool reported success (return code 0) but somehow no file
        # landed on disk -- must not be reported as a successful merge.
        output_path = tmp_path / "never_written.bin"
        monkeypatch.setattr(
            merge_worker_module, "FlashProcess",
            make_fake_process(SUCCESSFUL_LINES, return_code=0),
        )
        worker = MergeWorker(entries, "esp32", str(output_path))

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.start()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is False


class TestFailure:
    def test_nonzero_return_code_reports_failure_with_exit_code_message(self, qtbot, monkeypatch, tmp_path, entries):
        output_path = tmp_path / "merged.bin"
        monkeypatch.setattr(
            merge_worker_module, "FlashProcess",
            make_fake_process(["some error output"], return_code=2),
        )
        worker = MergeWorker(entries, "esp32", str(output_path))

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.start()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is False
        assert "exited with code 2" in result.error_message

    def test_missing_esptool_reports_clear_error(self, qtbot, monkeypatch, tmp_path, entries):
        def raise_not_found(command):
            raise FileNotFoundError("esptool")

        monkeypatch.setattr(merge_worker_module, "FlashProcess", raise_not_found)
        worker = MergeWorker(entries, "esp32", str(tmp_path / "merged.bin"))

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.start()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is False
        assert "could not be launched" in result.error_message


class TestCancel:
    def test_cancel_mid_merge_reports_cancelled(self, qtbot, monkeypatch, tmp_path, entries):
        monkeypatch.setattr(
            merge_worker_module, "FlashProcess",
            make_fake_process(SUCCESSFUL_LINES, return_code=0, block_after=1),
        )
        worker = MergeWorker(entries, "esp32", str(tmp_path / "merged.bin"))
        worker.start()
        qtbot.wait(100)

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.request_cancel()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is False
        assert "cancelled" in result.error_message.lower()

    def test_cancel_before_process_starts(self, qtbot, monkeypatch, tmp_path, entries):
        monkeypatch.setattr(
            merge_worker_module, "FlashProcess",
            make_fake_process(SUCCESSFUL_LINES, return_code=0),
        )
        worker = MergeWorker(entries, "esp32", str(tmp_path / "merged.bin"))
        worker.request_cancel()

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.start()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is False
        assert "cancelled" in result.error_message.lower()


class TestTimeout:
    def test_silent_process_past_timeout_is_terminated_and_reported(self, qtbot, monkeypatch, tmp_path, entries):
        # A process that never emits a line and never exits should be
        # terminated once MERGE_TIMEOUT_SECONDS has elapsed rather than
        # hanging the worker thread forever.
        monkeypatch.setattr(merge_worker_module, "MERGE_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(
            merge_worker_module, "_POLL_INTERVAL_SECONDS", 0.05,
        )

        class FakeSilentProcess:
            def __init__(self, command):
                self._terminated = threading.Event()

            def start(self) -> None:
                pass

            def iter_lines(self, stall_timeout=None):
                while not self._terminated.is_set():
                    yield None

            def wait(self, timeout=None) -> int:
                return -1

            def terminate(self) -> None:
                self._terminated.set()

        monkeypatch.setattr(merge_worker_module, "FlashProcess", FakeSilentProcess)
        worker = MergeWorker(entries, "esp32", str(tmp_path / "merged.bin"))

        with qtbot.waitSignal(worker.merge_finished, timeout=5000) as blocker:
            worker.start()

        (result,) = blocker.args
        worker.wait(2000)
        assert result.success is False
        assert "timed out" in result.error_message.lower()
