"""
Unit tests for FlashWorker._update_speed (app/workers/flash_worker.py).

Exercises the speed calculation directly (no QThread, no real subprocess)
by constructing a FlashWorker and calling its private _update_speed
method with synthetic esptool write-cursor addresses, monkeypatching
time.monotonic for determinism.
"""

from __future__ import annotations

import pytest

from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import SUPPORTED_CHIPS
from app.workers import flash_worker as flash_worker_module
from app.workers.flash_worker import FlashWorker


def _device_with_entries(*address_size_pairs):
    device = DeviceConfig(name="Device", com_port="COM3", chip_type=SUPPORTED_CHIPS[0])
    for address, size in address_size_pairs:
        entry = FirmwareEntry(file_path=f"/tmp/{address}.bin", address=address, enabled=True)
        entry.file_size = size
        device.add_firmware(entry)
    return device


def _worker(device):
    # stall_timeout is resolved eagerly by __init__ unless given -- pass
    # an explicit value so this never touches app_settings/os.environ.
    return FlashWorker(device, stall_timeout=45.0)


def _fake_clock(monkeypatch, times):
    """Feed `times` (an iterable of floats) to successive
    time.monotonic() calls made inside flash_worker.py."""
    it = iter(times)
    monkeypatch.setattr(flash_worker_module.time, "monotonic", lambda: next(it))


class TestUpdateSpeedSingleFile:
    def test_first_sample_falls_back_to_cumulative_average(self, monkeypatch):
        device = _device_with_entries(("0x10000", 4096))
        worker = _worker(device)
        speeds = []
        worker.speed_changed.connect(lambda dev_id, kbps: speeds.append(kbps))

        _fake_clock(monkeypatch, [10.0])  # only the sample-append call
        worker._update_speed("dev", start_time=9.0, address="0x10800")  # halfway through

        assert len(speeds) == 1
        # 2048 bytes done over 1.0s elapsed = 2.0 KiB/s
        assert speeds[0] == pytest.approx(2.0)

    def test_zero_size_firmware_emits_nothing(self):
        device = _device_with_entries(("0x10000", 0))
        worker = _worker(device)
        speeds = []
        worker.speed_changed.connect(lambda dev_id, kbps: speeds.append(kbps))
        worker._update_speed("dev", start_time=0.0, address="0x10000")
        assert speeds == []

    def test_invalid_address_emits_nothing(self):
        device = _device_with_entries(("0x10000", 4096))
        worker = _worker(device)
        speeds = []
        worker.speed_changed.connect(lambda dev_id, kbps: speeds.append(kbps))
        worker._update_speed("dev", start_time=0.0, address="not-hex")
        assert speeds == []

    def test_window_uses_only_recent_samples(self, monkeypatch):
        """
        A rolling window means throughput is computed from the delta
        between the newest sample and the oldest sample *still inside
        the window*, not from t=0 -- this is the actual bug being fixed
        (see flash_worker.py's docstring on _update_speed).
        """
        device = _device_with_entries(("0x10000", 100_000))
        worker = _worker(device)
        speeds = []
        worker.speed_changed.connect(lambda dev_id, kbps: speeds.append(kbps))

        # Sample 1 at t=0: cursor at start (0 bytes done) -- simulates a
        # slow initial connect/erase phase before any real writing.
        _fake_clock(monkeypatch, [0.0])
        worker._update_speed("dev", start_time=0.0, address="0x10000")

        # Sample 2 at t=10: still basically nothing written (slow phase
        # continues) -- 0 bytes over 10s.
        _fake_clock(monkeypatch, [10.0])
        worker._update_speed("dev", start_time=0.0, address="0x10000")

        # Sample 3 at t=10.5: a burst of real writing just happened --
        # 51200 bytes (half the file) written in the last 0.5s => fast.
        _fake_clock(monkeypatch, [10.5])
        worker._update_speed("dev", start_time=0.0, address="0x18000")

        last_speed = speeds[-1]
        # A whole-run cumulative average (the old, buggy behaviour) would
        # be roughly 50000 bytes / 10.5s / 1024 =~ 4.65 KiB/s -- badly
        # understating the burst that just happened. The rolling window
        # should report something much closer to the true instantaneous
        # rate of 51200 bytes over the visible window.
        cumulative_average = (50_000 / 1024.0) / 10.5
        assert last_speed > cumulative_average * 2


class TestUpdateSpeedMultiFile:
    def test_second_file_accounts_for_first_files_full_size(self, monkeypatch):
        """
        The core multi-file bug: esptool's write-cursor address resets to
        each file's own start address, but bytes-done must still count
        every earlier file's full size -- otherwise the reported speed
        would look like it dropped to near-zero the moment a second file
        starts writing.
        """
        device = _device_with_entries(("0x1000", 4096), ("0x10000", 4096))
        worker = _worker(device)
        speeds = []
        worker.speed_changed.connect(lambda dev_id, kbps: speeds.append(kbps))

        # First file fully written (cursor at its end).
        _fake_clock(monkeypatch, [0.0])
        worker._update_speed("dev", start_time=0.0, address="0x2000")
        # Second file: cursor halfway through it.
        _fake_clock(monkeypatch, [1.0])
        worker._update_speed("dev", start_time=0.0, address="0x10800")

        # bytes_done should be first file's 4096 + 2048 (halfway into the
        # second file) = 6144, not just 2048.
        oldest_time, oldest_bytes = worker._speed_samples[0]
        newest_time, newest_bytes = worker._speed_samples[-1]
        assert newest_bytes == 4096 + 2048

    def test_total_bytes_never_exceeds_sum_of_all_entries(self, monkeypatch):
        device = _device_with_entries(("0x1000", 4096), ("0x10000", 4096))
        worker = _worker(device)
        _fake_clock(monkeypatch, [0.0])
        # Cursor beyond the end of everything -- should clamp, not overflow.
        worker._update_speed("dev", start_time=0.0, address="0x20000")
        _, bytes_done = worker._speed_samples[-1]
        assert bytes_done == 4096 + 4096
