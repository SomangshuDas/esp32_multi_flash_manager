"""pytest-qt integration tests for app/controllers/project_controller.py."""

from __future__ import annotations

import pytest

from app.controllers.project_controller import ProjectController
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry


@pytest.fixture
def controller(qtbot):
    return ProjectController()


class TestNewProject:
    def test_new_project_resets_state(self, controller):
        controller.current_file_path = "/tmp/old.emfm"
        controller.dirty = True
        controller.new_project()
        assert controller.current_file_path is None
        assert controller.dirty is False
        assert controller.project.devices == []

    def test_new_project_emits_project_loaded(self, qtbot, controller):
        with qtbot.waitSignal(controller.project_loaded, timeout=1000) as blocker:
            controller.new_project()
        assert blocker.args == [controller.project]


class TestSaveProject:
    def test_save_to_explicit_path_succeeds_and_emits(self, qtbot, controller, tmp_path):
        path = tmp_path / "project.emfm"
        with qtbot.waitSignal(controller.project_saved, timeout=1000) as blocker:
            result = controller.save_project(str(path))
        assert result is True
        assert path.is_file()
        assert blocker.args == [str(path)]
        assert controller.current_file_path == str(path)
        assert controller.dirty is False

    def test_save_without_path_and_no_prior_path_fails(self, controller):
        assert controller.save_project(None) is False

    def test_save_reuses_current_file_path_when_none_given(self, controller, tmp_path):
        path = tmp_path / "project.emfm"
        controller.save_project(str(path))
        controller.project.project_name = "Renamed"
        assert controller.save_project() is True

    def test_save_to_bad_location_emits_load_failed(self, qtbot, controller, tmp_path):
        bad_path = tmp_path / "no_such_dir" / "project.emfm"
        with qtbot.waitSignal(controller.load_failed, timeout=1000):
            result = controller.save_project(str(bad_path))
        assert result is False


class TestOpenProject:
    def test_open_valid_project_emits_loaded(self, qtbot, controller, tmp_path):
        path = tmp_path / "project.emfm"
        controller.project.project_name = "To Reopen"
        controller.save_project(str(path))
        controller.new_project()

        with qtbot.waitSignal(controller.project_loaded, timeout=1000):
            result = controller.open_project(str(path))
        assert result is True
        assert controller.project.project_name == "To Reopen"
        assert controller.current_file_path == str(path)
        assert controller.dirty is False

    def test_open_missing_file_emits_load_failed_and_returns_false(self, qtbot, controller, tmp_path):
        with qtbot.waitSignal(controller.load_failed, timeout=1000):
            result = controller.open_project(str(tmp_path / "nope.emfm"))
        assert result is False

    def test_open_corrupt_file_emits_load_failed(self, qtbot, controller, tmp_path):
        path = tmp_path / "corrupt.emfm"
        path.write_text("{not json", encoding="utf-8")
        with qtbot.waitSignal(controller.load_failed, timeout=1000):
            result = controller.open_project(str(path))
        assert result is False

    def test_open_with_missing_firmware_emits_missing_firmware_detected(self, qtbot, controller, tmp_path):
        device = DeviceConfig(name="Bench 1")
        device.add_firmware(FirmwareEntry(file_path=str(tmp_path / "ghost.bin"), address="0x1000"))
        controller.project.add_device(device)
        path = tmp_path / "project.emfm"
        controller.save_project(str(path))

        with qtbot.waitSignal(controller.missing_firmware_detected, timeout=1000) as blocker:
            controller.open_project(str(path))
        missing_entries = blocker.args[0]
        assert len(missing_entries) == 1
        assert missing_entries[0].missing is True

    def test_open_without_missing_firmware_does_not_emit_missing_signal(self, qtbot, controller, tmp_path):
        device = DeviceConfig(name="Bench 1")
        firmware_path = tmp_path / "firmware.bin"
        firmware_path.write_bytes(b"\x00" * 16)
        device.add_firmware(FirmwareEntry(file_path=str(firmware_path), address="0x1000"))
        controller.project.add_device(device)
        path = tmp_path / "project.emfm"
        controller.save_project(str(path))

        with qtbot.assertNotEmitted(controller.missing_firmware_detected, wait=200):
            controller.open_project(str(path))


class TestMarkDirty:
    def test_mark_dirty_sets_flag(self, controller):
        assert controller.dirty is False
        controller.mark_dirty()
        assert controller.dirty is True


class TestLegacyProjectFileSupport:
    """Opening an old `.efmproj` file must still work, but must never let
    the app silently save back over it in the old format -- see
    ProjectController.open_project()'s legacy handling."""

    def _save_as_legacy(self, controller, tmp_path, name="legacy.efmproj"):
        """Write a project file directly (bypassing save_project(), which
        would just write wherever it's told regardless of extension) so
        the resulting file genuinely has the legacy extension."""
        from app.project_manager.project_io import save_project as raw_save_project

        path = tmp_path / name
        raw_save_project(controller.project, str(path))
        return path

    def test_opening_legacy_file_succeeds(self, controller, tmp_path):
        controller.project.project_name = "Old Project"
        path = self._save_as_legacy(controller, tmp_path)
        controller.new_project()

        result = controller.open_project(str(path))

        assert result is True
        assert controller.project.project_name == "Old Project"

    def test_opening_legacy_file_leaves_current_file_path_unset(self, controller, tmp_path):
        path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(path))
        assert controller.current_file_path is None

    def test_opening_legacy_file_marks_project_dirty(self, controller, tmp_path):
        """Forces the "unsaved changes" prompt / a Save As before the user
        can navigate away, rather than letting a re-save silently vanish."""
        path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(path))
        assert controller.dirty is True

    def test_opening_legacy_file_emits_legacy_project_loaded(self, qtbot, controller, tmp_path):
        path = self._save_as_legacy(controller, tmp_path)
        with qtbot.waitSignal(controller.legacy_project_loaded, timeout=1000) as blocker:
            controller.open_project(str(path))
        assert blocker.args == [str(path)]

    def test_opening_current_format_file_does_not_emit_legacy_signal(self, qtbot, controller, tmp_path):
        path = tmp_path / "current.emfm"
        controller.save_project(str(path))
        controller.new_project()
        with qtbot.assertNotEmitted(controller.legacy_project_loaded, wait=200):
            controller.open_project(str(path))

    def test_save_after_opening_legacy_file_requires_a_path(self, controller, tmp_path):
        """With current_file_path unset, a plain save_project(None) --
        the equivalent of the UI's "Save" action seeing no path to reuse --
        must fail rather than silently writing back to the old .efmproj
        location (MainWindow._on_save_project routes this case to Save As
        instead; see tests/ui/test_interface_lock.py and friends for the
        UI-level wiring)."""
        path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(path))
        assert controller.save_project(None) is False

    def test_explicit_save_as_after_legacy_open_writes_new_emfm_file_and_clears_dirty(self, controller, tmp_path):
        old_path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(old_path))

        new_path = tmp_path / "resaved.emfm"
        result = controller.save_project(str(new_path))

        assert result is True
        assert new_path.is_file()
        assert controller.current_file_path == str(new_path)
        assert controller.dirty is False
        # The original legacy file is left untouched, not overwritten.
        assert old_path.is_file()

    def test_case_insensitive_legacy_extension_is_still_detected(self, controller, tmp_path):
        path = self._save_as_legacy(controller, tmp_path, name="legacy.EFMPROJ")
        controller.open_project(str(path))
        assert controller.current_file_path is None
        assert controller.dirty is True

    def test_opening_legacy_file_sets_legacy_pending_migration(self, controller, tmp_path):
        path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(path))
        assert controller.legacy_pending_migration is True

    def test_opening_current_format_file_does_not_set_legacy_pending_migration(self, controller, tmp_path):
        path = tmp_path / "current.emfm"
        controller.save_project(str(path))
        controller.new_project()
        controller.open_project(str(path))
        assert controller.legacy_pending_migration is False

    def test_save_as_after_legacy_open_clears_legacy_pending_migration(self, controller, tmp_path):
        old_path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(old_path))
        assert controller.legacy_pending_migration is True

        controller.save_project(str(tmp_path / "resaved.emfm"))
        assert controller.legacy_pending_migration is False

    def test_new_project_clears_legacy_pending_migration(self, controller, tmp_path):
        path = self._save_as_legacy(controller, tmp_path)
        controller.open_project(str(path))
        assert controller.legacy_pending_migration is True

        controller.new_project()
        assert controller.legacy_pending_migration is False


class TestAutosave:
    """
    Coverage for ProjectController.autosave() itself -- previously only
    exercised indirectly (project_io.save_autosave_recovery/load_autosave_
    recovery have their own direct tests, and MainWindow._on_autosave_
    timeout is what actually calls this on a timer), so the routing
    logic in autosave() -- real re-save vs. crash-recovery-slot fallback
    -- had no dedicated test of its own.
    """

    def test_new_never_saved_dirty_project_goes_to_recovery_slot(self, controller):
        """A brand-new project (current_file_path is None) that has
        unsaved changes must be protected via the crash-recovery slot,
        not silently skipped -- see project_controller.py's autosave()
        docstring and the 0.12.0 release notes' "Changed" entry for
        this exact fix."""
        controller.project.project_name = "Never Saved Yet"
        controller.mark_dirty()

        controller.autosave()

        assert controller.current_file_path is None  # never treated as a real save
        assert controller.dirty is True  # dirty flag is untouched by the safety net
        assert ProjectController.has_recoverable_autosave() is True

    def test_new_project_with_no_changes_does_not_create_a_recovery_slot(self, controller):
        """A brand-new, still-untouched project has nothing worth
        protecting -- autosave() must not manufacture a recovery slot
        out of an empty, never-edited project."""
        assert controller.dirty is False

        controller.autosave()

        assert ProjectController.has_recoverable_autosave() is False

    def test_already_saved_project_re_saves_in_place_not_to_recovery_slot(self, controller, tmp_path):
        """Once a project has a real current_file_path, autosave() must
        re-save it there directly rather than routing to the
        crash-recovery slot (which is reserved for the never-saved
        case)."""
        path = tmp_path / "project.emfm"
        controller.save_project(str(path))
        controller.mark_dirty()

        controller.autosave()

        assert controller.dirty is False
        assert path.is_file()
        assert ProjectController.has_recoverable_autosave() is False

    def test_real_save_discards_any_pending_recovery_slot(self, controller, tmp_path):
        """Once the user does a real Save, the earlier crash-recovery
        copy (from before that save) is no longer needed and must be
        cleaned up -- see save_project()'s discard_autosave_recovery()
        call -- so a stale recovery slot never gets offered back to the
        user after they've already saved for real."""
        controller.project.project_name = "Will Be Saved For Real"
        controller.mark_dirty()
        controller.autosave()
        assert ProjectController.has_recoverable_autosave() is True

        controller.save_project(str(tmp_path / "project.emfm"))

        assert ProjectController.has_recoverable_autosave() is False
