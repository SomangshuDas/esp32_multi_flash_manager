"""Unit tests for app/firmware_manager/bin_merge.py."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from app.firmware_manager.bin_merge import (
    MergeResult,
    MergeSeverity,
    firmware_bin_folder,
    run_merge,
    validate_merge_entries,
)
from app.models.firmware_model import FirmwareEntry
from app.utilities.chip_detect import AUTO_CHIP


def _entry(tmp_path, name: str, address: str, size: int = 256) -> FirmwareEntry:
    path = tmp_path / name
    path.write_bytes(b"\x00" * size)
    return FirmwareEntry(file_path=str(path), address=address)


def _errors(report) -> list[str]:
    return [i.message for i in report.issues if i.severity == MergeSeverity.ERROR]


def _warnings(report) -> list[str]:
    return [i.message for i in report.issues if i.severity == MergeSeverity.WARNING]


class TestValidateMergeEntriesBasics:
    def test_empty_entries_is_error(self, tmp_path):
        report = validate_merge_entries([], chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert report.has_errors
        assert any("Select at least one" in m for m in _errors(report))

    def test_auto_chip_is_error(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip=AUTO_CHIP, output_path=str(tmp_path / "out.bin"))
        assert any("specific chip must be selected" in m for m in _errors(report))

    def test_no_chip_is_error(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="", output_path=str(tmp_path / "out.bin"))
        assert any("specific chip must be selected" in m for m in _errors(report))

    def test_valid_specific_chip_is_fine(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert not any("chip must be selected" in m for m in _errors(report))


class TestValidateMergeEntriesOutputPath:
    def test_blank_output_path_is_error(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="esp32", output_path="")
        assert any("Choose an output file" in m for m in _errors(report))

    def test_whitespace_only_output_path_is_error(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="esp32", output_path="   ")
        assert any("Choose an output file" in m for m in _errors(report))

    def test_output_folder_does_not_exist_is_error(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        bad_path = tmp_path / "nonexistent_dir" / "merged.bin"
        report = validate_merge_entries(entries, chip="esp32", output_path=str(bad_path))
        assert any("Output folder does not exist" in m for m in _errors(report))

    def test_output_path_that_is_a_directory_is_error(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(tmp_path))
        assert any("not a file" in m for m in _errors(report))

    def test_existing_output_file_is_warning_not_error(self, tmp_path):
        existing = tmp_path / "merged.bin"
        existing.write_bytes(b"old content")
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(existing))
        assert any("already exists" in m for m in _warnings(report))
        assert not any("already exists" in m for m in _errors(report))

    def test_valid_new_output_path_produces_no_output_issue(self, tmp_path):
        entries = [_entry(tmp_path, "bootloader.bin", "0x1000")]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(tmp_path / "merged.bin"))
        assert not any("Output" in m or "output file" in m for m in _errors(report) + _warnings(report))


class TestValidateMergeEntriesPerFile:
    def test_missing_file_path_is_error(self):
        entry = FirmwareEntry(file_path="", address="0x1000")
        report = validate_merge_entries([entry], chip="esp32", output_path="/tmp/out.bin")
        assert any("no file" in m for m in _errors(report))

    def test_file_missing_on_disk_is_error(self, tmp_path):
        entry = FirmwareEntry(file_path=str(tmp_path / "ghost.bin"), address="0x1000")
        report = validate_merge_entries([entry], chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert any("missing on disk" in m for m in _errors(report))

    def test_invalid_address_is_error(self, tmp_path):
        entry = _entry(tmp_path, "app.bin", "not-hex")
        report = validate_merge_entries([entry], chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert any("Invalid flash address" in m for m in _errors(report))

    def test_duplicate_addresses_is_error(self, tmp_path):
        entries = [
            _entry(tmp_path, "a.bin", "0x1000"),
            _entry(tmp_path, "b.bin", "0x1000"),
        ]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert any("Duplicate flash address" in m for m in _errors(report))

    def test_zero_byte_file_is_warning(self, tmp_path):
        entry = _entry(tmp_path, "empty.bin", "0x1000", size=0)
        report = validate_merge_entries([entry], chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert any("0 bytes" in m for m in _warnings(report))

    def test_overlapping_regions_is_error(self, tmp_path):
        entries = [
            _entry(tmp_path, "a.bin", "0x0", size=0x4000),
            _entry(tmp_path, "b.bin", "0x1000", size=0x1000),
        ]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert any("overlaps" in m for m in _errors(report))

    def test_non_overlapping_entries_are_valid(self, tmp_path):
        entries = [
            _entry(tmp_path, "bootloader.bin", "0x1000", size=0x1000),
            _entry(tmp_path, "partitions.bin", "0x8000", size=0x1000),
            _entry(tmp_path, "app.bin", "0x10000", size=0x1000),
        ]
        report = validate_merge_entries(entries, chip="esp32", output_path=str(tmp_path / "out.bin"))
        assert not report.has_errors


class TestFirmwareBinFolder:
    def test_returns_none_for_empty_list(self):
        assert firmware_bin_folder([]) is None

    def test_returns_none_when_no_entries_have_a_path(self):
        assert firmware_bin_folder([FirmwareEntry(file_path="")]) is None

    def test_prefers_folder_of_firmware_bin(self, tmp_path):
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        fw_dir = tmp_path / "fw"
        fw_dir.mkdir()
        entries = [
            FirmwareEntry(file_path=str(other_dir / "bootloader.bin")),
            FirmwareEntry(file_path=str(fw_dir / "firmware.bin")),
        ]
        assert firmware_bin_folder(entries) == str(fw_dir)

    def test_firmware_bin_match_is_case_insensitive(self, tmp_path):
        fw_dir = tmp_path / "fw"
        entries = [FirmwareEntry(file_path=str(fw_dir / "FIRMWARE.BIN"))]
        assert firmware_bin_folder(entries) == str(fw_dir)

    def test_falls_back_to_first_entry_with_a_path(self, tmp_path):
        first_dir = tmp_path / "first"
        entries = [
            FirmwareEntry(file_path=""),
            FirmwareEntry(file_path=str(first_dir / "bootloader.bin")),
            FirmwareEntry(file_path=str((tmp_path / "second") / "app.bin")),
        ]
        assert firmware_bin_folder(entries) == str(first_dir)


class TestRunMerge:
    def _entries(self, tmp_path):
        return [_entry(tmp_path, "bootloader.bin", "0x1000")]

    def test_success_when_subprocess_ok_and_output_file_exists(self, tmp_path):
        output_path = tmp_path / "merged.bin"

        def fake_run(command, **kwargs):
            output_path.write_bytes(b"merged content")
            return subprocess.CompletedProcess(command, returncode=0, stdout="Wrote merged image\n")

        with patch("app.firmware_manager.bin_merge.subprocess.run", side_effect=fake_run):
            result = run_merge(self._entries(tmp_path), chip="esp32", output_path=str(output_path))

        assert isinstance(result, MergeResult)
        assert result.success is True
        assert result.output_path == str(output_path)

    def test_failure_when_returncode_nonzero(self, tmp_path):
        output_path = tmp_path / "merged.bin"

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, returncode=1, stdout="some esptool error\n")

        with patch("app.firmware_manager.bin_merge.subprocess.run", side_effect=fake_run):
            result = run_merge(self._entries(tmp_path), chip="esp32", output_path=str(output_path))

        assert result.success is False
        assert "exited with code 1" in result.error_message

    def test_failure_when_output_file_not_actually_created(self, tmp_path):
        output_path = tmp_path / "merged.bin"

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, returncode=0, stdout="")

        with patch("app.firmware_manager.bin_merge.subprocess.run", side_effect=fake_run):
            result = run_merge(self._entries(tmp_path), chip="esp32", output_path=str(output_path))

        assert result.success is False

    def test_esptool_not_found_reported_gracefully(self, tmp_path):
        with patch("app.firmware_manager.bin_merge.subprocess.run", side_effect=FileNotFoundError("no esptool")):
            result = run_merge(self._entries(tmp_path), chip="esp32", output_path=str(tmp_path / "merged.bin"))
        assert result.success is False
        assert "could not be launched" in result.error_message

    def test_timeout_reported_gracefully(self, tmp_path):
        timeout_exc = subprocess.TimeoutExpired(cmd=["esptool"], timeout=180, output="partial output")
        with patch("app.firmware_manager.bin_merge.subprocess.run", side_effect=timeout_exc):
            result = run_merge(self._entries(tmp_path), chip="esp32", output_path=str(tmp_path / "merged.bin"))
        assert result.success is False
        assert "timed out" in result.error_message

    def test_unexpected_exception_reported_gracefully(self, tmp_path):
        with patch("app.firmware_manager.bin_merge.subprocess.run", side_effect=RuntimeError("boom")):
            result = run_merge(self._entries(tmp_path), chip="esp32", output_path=str(tmp_path / "merged.bin"))
        assert result.success is False
        assert "Unexpected error" in result.error_message
