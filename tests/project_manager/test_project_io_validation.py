"""
Tests for the input-validation hardening added to
app/project_manager/project_io.py's load_project(): a file-size cap
(MAX_PROJECT_FILE_SIZE_BYTES) checked before parsing, and post-parse caps
on device count (MAX_DEVICES_PER_PROJECT) and firmware-entries-per-device
(MAX_FIRMWARE_ENTRIES_PER_DEVICE). See docs/THREAT_MODEL.md.
"""

from __future__ import annotations

import json

import pytest

from app.project_manager.project_io import ProjectLoadError, load_project
from app.utilities.constants import (
    MAX_DEVICES_PER_PROJECT,
    MAX_FIRMWARE_ENTRIES_PER_DEVICE,
    MAX_PROJECT_FILE_SIZE_BYTES,
)


def _write(tmp_path, data: dict, name: str = "project.emfm"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestFileSizeCap:
    def test_oversized_file_is_rejected_before_parsing(self, tmp_path):
        path = tmp_path / "huge.emfm"
        # Write a file just over the cap without needing MAX_PROJECT_FILE_SIZE_BYTES
        # worth of real memory pressure in the test itself.
        with path.open("wb") as handle:
            handle.seek(MAX_PROJECT_FILE_SIZE_BYTES)
            handle.write(b"0")
        with pytest.raises(ProjectLoadError, match="larger than"):
            load_project(str(path))

    def test_normal_sized_file_loads_fine(self, tmp_path):
        path = _write(tmp_path, {"project_name": "Small", "devices": []})
        project = load_project(str(path))
        assert project.project_name == "Small"


class TestDeviceCountCap:
    def test_too_many_devices_is_rejected(self, tmp_path):
        devices = [{"name": f"Device {i}"} for i in range(MAX_DEVICES_PER_PROJECT + 1)]
        path = _write(tmp_path, {"project_name": "Huge", "devices": devices})
        with pytest.raises(ProjectLoadError, match="devices"):
            load_project(str(path))

    def test_device_count_at_cap_is_accepted(self, tmp_path):
        devices = [{"name": f"Device {i}"} for i in range(MAX_DEVICES_PER_PROJECT)]
        path = _write(tmp_path, {"project_name": "AtCap", "devices": devices})
        project = load_project(str(path))
        assert len(project.devices) == MAX_DEVICES_PER_PROJECT


class TestFirmwareEntryCountCap:
    def test_too_many_firmware_entries_is_rejected(self, tmp_path):
        firmware = [
            {"file_path": f"fw_{i}.bin", "address": "0x1000"}
            for i in range(MAX_FIRMWARE_ENTRIES_PER_DEVICE + 1)
        ]
        path = _write(
            tmp_path,
            {"project_name": "Huge FW", "devices": [{"name": "Device 1", "firmware": firmware}]},
        )
        with pytest.raises(ProjectLoadError, match="firmware entries"):
            load_project(str(path))

    def test_firmware_entry_count_at_cap_is_accepted(self, tmp_path):
        firmware = [
            {"file_path": f"fw_{i}.bin", "address": "0x1000"}
            for i in range(MAX_FIRMWARE_ENTRIES_PER_DEVICE)
        ]
        path = _write(
            tmp_path,
            {"project_name": "AtCap FW", "devices": [{"name": "Device 1", "firmware": firmware}]},
        )
        project = load_project(str(path))
        assert len(project.devices[0].firmware) == MAX_FIRMWARE_ENTRIES_PER_DEVICE


class TestMalformedShapesDoNotCrashValidation:
    def test_non_dict_root_is_left_to_from_dict_to_reject(self, tmp_path):
        path = _write(tmp_path, [], name="listroot.emfm")
        with pytest.raises(ProjectLoadError):
            load_project(str(path))

    def test_devices_not_a_list_is_left_to_from_dict_to_reject(self, tmp_path):
        path = _write(tmp_path, {"project_name": "Bad", "devices": "not-a-list"})
        with pytest.raises(ProjectLoadError):
            load_project(str(path))

    def test_device_entry_not_a_dict_is_skipped_by_validation_not_crashed(self, tmp_path):
        # A non-dict device entry must not raise inside _validate_project_shape
        # itself -- it's ProjectModel.from_dict's job to reject this shape.
        path = _write(tmp_path, {"project_name": "Bad", "devices": ["not-a-dict"]})
        with pytest.raises(ProjectLoadError):
            load_project(str(path))
