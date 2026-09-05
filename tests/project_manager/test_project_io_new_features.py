"""
Unit tests for the new behavior added to app/project_manager/project_io.py:
- firmware path relativization/absolutization (§12.10)
- advisory project locking (§12.9)
- crash-recovery autosave slot (§12.8)
- atomic writes are already covered by test_project_io.py's existing
  "unwritable location" case plus the fuzz suite -- these tests focus on
  the NEW behaviors only.
"""

from __future__ import annotations

import os

import pytest

from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel
from app.project_manager import project_io
from app.project_manager.project_io import (
    ProjectLockError,
    load_project,
    save_project,
)


def _project_with_firmware(firmware_path: str) -> ProjectModel:
    project = ProjectModel(project_name="Line A")
    device = DeviceConfig(name="Bench 1", com_port="COM3")
    device.add_firmware(FirmwareEntry(file_path=firmware_path, address="0x10000"))
    project.add_device(device)
    return project


class TestFirmwarePathRelativization:
    def test_saved_file_stores_relative_path_when_possible(self, tmp_path):
        firmware_dir = tmp_path / "firmware"
        firmware_dir.mkdir()
        firmware_path = firmware_dir / "app.bin"
        firmware_path.write_bytes(b"\x00" * 64)

        project = _project_with_firmware(str(firmware_path))
        project_path = tmp_path / "project.emfm"
        save_project(project, str(project_path))

        import json
        with project_path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        stored_path = raw["devices"][0]["firmware"][0]["file_path"]
        assert not os.path.isabs(stored_path)
        assert stored_path == os.path.join("firmware", "app.bin")

    def test_loaded_relative_path_resolves_to_absolute_in_memory(self, tmp_path):
        firmware_dir = tmp_path / "firmware"
        firmware_dir.mkdir()
        firmware_path = firmware_dir / "app.bin"
        firmware_path.write_bytes(b"\x00" * 64)

        project = _project_with_firmware(str(firmware_path))
        project_path = tmp_path / "project.emfm"
        save_project(project, str(project_path))

        restored = load_project(str(project_path))
        restored_path = restored.devices[0].firmware[0].file_path
        assert os.path.isabs(restored_path)
        assert os.path.samefile(restored_path, firmware_path)

    def test_project_survives_being_moved_with_its_firmware(self, tmp_path):
        """
        The actual bug being fixed: previously an absolute path baked in
        at save time only ever resolved on the exact machine/directory
        layout it was saved from. Moving the whole folder (project +
        firmware together, preserving their relative layout) must still
        resolve correctly afterwards.
        """
        original_root = tmp_path / "original_location"
        original_root.mkdir()
        (original_root / "firmware").mkdir()
        firmware_path = original_root / "firmware" / "app.bin"
        firmware_path.write_bytes(b"\x00" * 64)
        project = _project_with_firmware(str(firmware_path))
        project_path = original_root / "project.emfm"
        save_project(project, str(project_path))

        # Simulate moving the whole folder tree to a new location.
        import shutil
        new_root = tmp_path / "new_location"
        shutil.move(str(original_root), str(new_root))

        restored = load_project(str(new_root / "project.emfm"))
        restored_entry = restored.devices[0].firmware[0]
        assert not restored_entry.missing

    def test_legacy_absolute_path_file_still_loads(self, tmp_path):
        """A project saved by a pre-fix release has an absolute path
        baked in -- must still load correctly (not be force-relativized
        or broken on read)."""
        firmware_path = tmp_path / "app.bin"
        firmware_path.write_bytes(b"\x00" * 64)
        project_path = tmp_path / "project.emfm"

        import json
        legacy_data = {
            "schema_version": "0.9.0",
            "project_name": "Legacy",
            "devices": [
                {
                    "id": "dev-1", "name": "Bench 1", "com_port": "COM3",
                    "firmware": [{"file_path": str(firmware_path), "address": "0x10000", "enabled": True}],
                }
            ],
        }
        with project_path.open("w", encoding="utf-8") as handle:
            json.dump(legacy_data, handle)

        restored = load_project(str(project_path))
        assert not restored.devices[0].firmware[0].missing


class TestProjectLocking:
    def test_acquire_then_read_reflects_current_process(self, tmp_path):
        project_path = str(tmp_path / "project.emfm")
        info = project_io.acquire_project_lock(project_path)
        assert info is not None
        assert info.pid == os.getpid()

        read_back = project_io.read_project_lock(project_path)
        assert read_back is not None
        assert read_back.pid == os.getpid()

    def test_release_removes_lock_sidecar(self, tmp_path):
        project_path = str(tmp_path / "project.emfm")
        project_io.acquire_project_lock(project_path)
        project_io.release_project_lock(project_path)
        assert project_io.read_project_lock(project_path) is None

    def test_reacquiring_own_lock_succeeds(self, tmp_path):
        project_path = str(tmp_path / "project.emfm")
        project_io.acquire_project_lock(project_path)
        # Re-saving/re-opening the same project in the same process must
        # never lock itself out.
        info = project_io.acquire_project_lock(project_path)
        assert info is not None

    def test_foreign_active_lock_raises(self, tmp_path):
        from datetime import datetime

        project_path = str(tmp_path / "project.emfm")
        lock_path = project_io._lock_path_for(project_path)
        import json
        with lock_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {"holder": "someoneelse@otherhost", "pid": 999999, "acquired_at": datetime.now().astimezone().isoformat()},
                handle,
            )
        with pytest.raises(ProjectLockError):
            project_io.acquire_project_lock(project_path)

    def test_stale_lock_by_age_does_not_raise(self, tmp_path):
        from datetime import datetime, timedelta

        project_path = str(tmp_path / "project.emfm")
        lock_path = project_io._lock_path_for(project_path)
        ancient = datetime.now().astimezone() - timedelta(days=10)
        import json
        with lock_path.open("w", encoding="utf-8") as handle:
            json.dump({"holder": "someoneelse@otherhost", "pid": 999999, "acquired_at": ancient.isoformat()}, handle)
        # Should not raise -- the lock is old enough to be considered abandoned.
        info = project_io.acquire_project_lock(project_path)
        assert info is not None

    def test_release_never_removes_a_foreign_lock(self, tmp_path):
        from datetime import datetime

        project_path = str(tmp_path / "project.emfm")
        lock_path = project_io._lock_path_for(project_path)
        import json
        with lock_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {"holder": "someoneelse@otherhost", "pid": os.getpid(), "acquired_at": datetime.now().astimezone().isoformat()},
                handle,
            )
        project_io.release_project_lock(project_path)
        assert lock_path.is_file()  # untouched -- different holder string

    def test_lock_sidecar_filename_is_dot_prefixed_hidden(self, tmp_path):
        """The lock sidecar must read as a hidden dotfile next to the
        project it guards (e.g. ".project.emfm.lock"), not a plainly
        visible "project.emfm.lock" sitting right alongside the user's
        own project file in their file browser."""
        project_path = str(tmp_path / "project.emfm")
        info = project_io.acquire_project_lock(project_path)
        assert info is not None
        assert info.lock_path.name == ".project.emfm.lock"
        assert info.lock_path.parent == tmp_path
        assert info.lock_path.is_file()


class TestAutosaveRecoverySlot:
    def test_no_recovery_slot_by_default(self):
        assert project_io.has_autosave_recovery() is False
        assert project_io.load_autosave_recovery() is None

    def test_save_then_load_round_trips(self, tmp_path):
        project = ProjectModel(project_name="Unsaved Work")
        project_io.save_autosave_recovery(project)
        assert project_io.has_autosave_recovery() is True

        recovered = project_io.load_autosave_recovery()
        assert recovered is not None
        assert recovered.project_name == "Unsaved Work"

    def test_discard_removes_the_slot(self):
        project = ProjectModel(project_name="Unsaved Work")
        project_io.save_autosave_recovery(project)
        project_io.discard_autosave_recovery()
        assert project_io.has_autosave_recovery() is False

    def test_discard_when_nothing_exists_does_not_raise(self):
        project_io.discard_autosave_recovery()  # should be a no-op, not an error
