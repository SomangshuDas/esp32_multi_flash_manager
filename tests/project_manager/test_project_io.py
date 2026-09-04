"""Unit tests for app/project_manager/project_io.py (non-fuzz cases)."""

from __future__ import annotations

import json

import pytest

from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel
from app.project_manager import project_io
from app.project_manager.project_io import ProjectLoadError, load_project, save_project


class TestSaveProject:
    def test_writes_readable_json_file(self, tmp_path):
        project = ProjectModel(project_name="My Project")
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        assert path.is_file()
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["project_name"] == "My Project"

    def test_adds_to_recent_projects(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        assert str(path) in project_io.get_recent_projects()

    def test_unwritable_location_raises_project_load_error(self, tmp_path):
        project = ProjectModel()
        bad_path = tmp_path / "no_such_dir" / "project.emfm"
        with pytest.raises(ProjectLoadError):
            save_project(project, str(bad_path))


class TestLoadProject:
    def test_roundtrip_with_devices_and_firmware(self, tmp_path):
        project = ProjectModel(project_name="Line A")
        device = DeviceConfig(name="Bench 1", com_port="COM3")
        firmware_path = tmp_path / "firmware.bin"
        firmware_path.write_bytes(b"\x00" * 128)
        device.add_firmware(FirmwareEntry(file_path=str(firmware_path), address="0x10000"))
        project.add_device(device)

        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        restored = load_project(str(path))

        assert restored.project_name == "Line A"
        assert len(restored.devices) == 1
        assert restored.devices[0].name == "Bench 1"
        assert restored.devices[0].firmware[0].missing is False
        assert restored.devices[0].firmware[0].file_size == 128

    def test_missing_firmware_is_not_fatal_but_flagged(self, tmp_path):
        project = ProjectModel()
        device = DeviceConfig(name="Bench 1")
        device.add_firmware(FirmwareEntry(file_path=str(tmp_path / "ghost.bin"), address="0x1000"))
        project.add_device(device)

        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        restored = load_project(str(path))

        assert restored.devices[0].firmware[0].missing is True

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(ProjectLoadError):
            load_project(str(tmp_path / "nope.emfm"))

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.emfm"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ProjectLoadError):
            load_project(str(path))

    def test_load_adds_to_recent_projects(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        project_io.clear_recent_projects()
        assert project_io.get_recent_projects() == []
        load_project(str(path))
        assert str(path) in project_io.get_recent_projects()


class TestRecentProjects:
    def test_clear_recent_projects(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        project_io.clear_recent_projects()
        assert project_io.get_recent_projects() == []

    def test_recent_projects_filters_deleted_files(self, tmp_path):
        project = ProjectModel()
        path = tmp_path / "project.emfm"
        save_project(project, str(path))
        path.unlink()
        assert str(path) not in project_io.get_recent_projects()

    def test_recent_projects_most_recent_first_and_deduplicated(self, tmp_path):
        project = ProjectModel()
        project_io.clear_recent_projects()
        path_a = tmp_path / "a.emfm"
        path_b = tmp_path / "b.emfm"
        save_project(project, str(path_a))
        save_project(project, str(path_b))
        save_project(project, str(path_a))  # re-saving A should move it back to the front

        recents = project_io.get_recent_projects()
        assert recents[0] == str(path_a)
        assert recents.count(str(path_a)) == 1

    def test_recent_projects_capped_at_max(self, tmp_path):
        from app.utilities.constants import MAX_RECENT_PROJECTS

        project = ProjectModel()
        project_io.clear_recent_projects()
        for i in range(MAX_RECENT_PROJECTS + 5):
            path = tmp_path / f"project_{i}.emfm"
            save_project(project, str(path))
        assert len(project_io.get_recent_projects()) <= MAX_RECENT_PROJECTS
