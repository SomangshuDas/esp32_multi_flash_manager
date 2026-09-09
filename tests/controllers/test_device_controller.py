"""
pytest-qt integration tests for app/controllers/device_controller.py.

These exercise the controller against a real ProjectModel and rely on
pytest-qt's `qtbot` fixture to assert Qt signals actually fire, since
DeviceController is a QObject and the UI depends on those signals for
live updates.
"""

from __future__ import annotations

import copy

import pytest

from app.controllers.device_controller import DeviceController
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel


@pytest.fixture
def controller(qtbot):
    project = ProjectModel()
    ctrl = DeviceController(project)
    qtbot.addWidget  # no-op reference to make intent clear; QObject has no widget to add
    return ctrl


class TestAddRemoveDuplicate:
    def test_add_device_appends_and_emits_signal(self, qtbot, controller):
        with qtbot.waitSignal(controller.device_added, timeout=1000) as blocker:
            device = controller.add_device("Bench 1")
        assert device in controller.devices()
        assert blocker.args == [device.id]

    def test_add_device_uses_default_settings_when_none_configured(self, controller):
        from app.utilities.constants import DEFAULT_BAUD, DEFAULT_FLASH_MODE

        device = controller.add_device()
        assert device.baud_rate == DEFAULT_BAUD
        assert device.flash_mode == DEFAULT_FLASH_MODE

    def test_add_device_applies_default_device_profile_when_configured(self, controller):
        from app.firmware_manager.profiles import FirmwareProfile, save_profile
        from app.utilities.app_settings import get_settings
        from app.utilities.constants import SETTINGS_KEY_DEFAULT_DEVICE_PROFILE

        profile = FirmwareProfile(name="RFID Reader", chip_type="esp32s3", baud_rate=921600)
        save_profile(profile)
        get_settings().setValue(SETTINGS_KEY_DEFAULT_DEVICE_PROFILE, "RFID Reader")

        device = controller.add_device()
        assert device.chip_type == "esp32s3"
        assert device.baud_rate == 921600

    def test_add_device_ignores_missing_default_profile(self, controller):
        """A configured default-profile name that no longer exists (e.g.
        the profile was deleted) must not block adding a device."""
        from app.utilities.app_settings import get_settings
        from app.utilities.constants import DEFAULT_BAUD, SETTINGS_KEY_DEFAULT_DEVICE_PROFILE

        get_settings().setValue(SETTINGS_KEY_DEFAULT_DEVICE_PROFILE, "Does Not Exist")

        device = controller.add_device()
        assert device.baud_rate == DEFAULT_BAUD

    def test_import_from_csv_adds_devices_and_emits_signals(self, qtbot, controller, tmp_path):
        csv_path = tmp_path / "devices.csv"
        csv_path.write_text("name,com_port\nDevice A,COM3\nDevice B,COM4\n", encoding="utf-8")

        with qtbot.waitSignals([controller.device_added, controller.device_added], timeout=1000):
            result = controller.import_from_csv(str(csv_path))

        assert result.imported_count == 2
        assert result.errors == []
        names = {d.name for d in controller.devices()}
        assert {"Device A", "Device B"} <= names

    def test_import_from_csv_applies_default_device_profile(self, controller, tmp_path):
        from app.firmware_manager.profiles import FirmwareProfile, save_profile
        from app.utilities.app_settings import get_settings
        from app.utilities.constants import SETTINGS_KEY_DEFAULT_DEVICE_PROFILE

        save_profile(FirmwareProfile(name="RFID Reader", chip_type="esp32s3", baud_rate=921600))
        get_settings().setValue(SETTINGS_KEY_DEFAULT_DEVICE_PROFILE, "RFID Reader")

        csv_path = tmp_path / "devices.csv"
        csv_path.write_text("name\nDevice A\n", encoding="utf-8")
        result = controller.import_from_csv(str(csv_path))

        assert result.devices[0].chip_type == "esp32s3"
        assert result.devices[0].baud_rate == 921600

    def test_import_from_csv_partial_success_reports_errors(self, controller, tmp_path):
        csv_path = tmp_path / "devices.csv"
        csv_path.write_text("name,com_port\nDevice A,COM3\n,COM4\n", encoding="utf-8")
        result = controller.import_from_csv(str(csv_path))
        assert result.imported_count == 1
        assert len(result.errors) == 1

    def test_remove_device_emits_signal_and_removes(self, qtbot, controller):
        device = controller.add_device("Bench 1")
        with qtbot.waitSignal(controller.device_removed, timeout=1000) as blocker:
            controller.remove_device(device.id)
        assert controller.get_device(device.id) is None
        assert blocker.args == [device.id]

    def test_remove_unknown_device_does_not_emit(self, qtbot, controller):
        controller.add_device("Bench 1")
        with qtbot.assertNotEmitted(controller.device_removed, wait=200):
            controller.remove_device("does-not-exist")

    def test_duplicate_device_creates_clone_and_emits(self, qtbot, controller):
        original = controller.add_device("Bench 1")
        original.com_port = "COM3"
        with qtbot.waitSignal(controller.device_added, timeout=1000) as blocker:
            clone = controller.duplicate_device(original.id)
        assert clone is not None
        assert clone.id != original.id
        assert clone.com_port == ""  # clone never steals the port
        assert blocker.args == [clone.id]

    def test_duplicate_unknown_device_returns_none(self, controller):
        assert controller.duplicate_device("does-not-exist") is None


class TestNotifyUpdated:
    def test_notify_updated_emits_device_updated(self, qtbot, controller):
        device = controller.add_device()
        with qtbot.waitSignal(controller.device_updated, timeout=1000) as blocker:
            controller.notify_updated(device.id)
        assert blocker.args == [device.id]


class TestApplyToAllAndSelected:
    def test_apply_to_all_sets_field_on_every_device(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        controller.apply_to_all("baud_rate", 921600)
        assert a.baud_rate == 921600
        assert b.baud_rate == 921600

    def test_apply_to_all_emits_once_per_device(self, qtbot, controller):
        controller.add_device("A")
        controller.add_device("B")
        received = []
        controller.device_updated.connect(lambda device_id: received.append(device_id))
        controller.apply_to_all("baud_rate", 460800)
        assert len(received) == 2

    def test_apply_to_all_ignores_unknown_field(self, controller):
        device = controller.add_device()
        controller.apply_to_all("totally_made_up_field", 42)
        assert not hasattr(device, "totally_made_up_field")

    def test_apply_to_selected_only_touches_selected_ids(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        controller.apply_to_selected([a.id], "baud_rate", 230400)
        assert a.baud_rate == 230400
        assert b.baud_rate != 230400

    def test_apply_to_selected_skips_unknown_ids_silently(self, controller):
        a = controller.add_device("A")
        # Must not raise even though one id doesn't exist.
        controller.apply_to_selected([a.id, "ghost-id"], "baud_rate", 115200)
        assert a.baud_rate == 115200


class TestApplyFirmwareToDevices:
    def _entries(self):
        return [
            FirmwareEntry(file_path="/tmp/bootloader.bin", address="0x1000"),
            FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000"),
        ]

    def test_replaces_firmware_list_with_independent_copies(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        entries = self._entries()
        updated = controller.apply_firmware_to_devices([a.id, b.id], entries)
        assert updated == 2
        assert len(a.firmware) == 2
        assert len(b.firmware) == 2
        # Independent copies -- editing one device's firmware entry must
        # not affect the other device's or the source entries.
        a.firmware[0].address = "0x2000"
        assert b.firmware[0].address == "0x1000"
        assert entries[0].address == "0x1000"

    def test_skips_unknown_device_ids(self, controller):
        a = controller.add_device("A")
        updated = controller.apply_firmware_to_devices([a.id, "ghost"], self._entries())
        assert updated == 1

    def test_empty_device_list_returns_zero(self, controller):
        assert controller.apply_firmware_to_devices([], self._entries()) == 0


class _FakeFlashController:
    """Stand-in for FlashController.is_busy() that never actually launches
    a worker -- just enough for DeviceController's busy-guard to consult."""

    def __init__(self, busy_ids: set[str]):
        self._busy_ids = busy_ids

    def is_busy(self, device_id: str) -> bool:
        return device_id in self._busy_ids


class TestBusyDeviceGuard:
    """
    Traceability bug fix: apply_to_all/apply_to_selected/
    apply_firmware_to_devices used to mutate a DeviceConfig regardless of
    whether FlashController.is_busy() was true for it. Because FlashWorker
    holds a live reference to that same object, renaming a device or
    reassigning its port mid-flash via Batch Edit made the resulting
    history entry reflect the new values rather than what was actually
    flashed. These tests confirm the guard closes that race.
    """

    def _entries(self):
        return [FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000")]

    def test_apply_to_all_skips_busy_device(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        controller.set_flash_controller(_FakeFlashController({a.id}))
        controller.apply_to_all("baud_rate", 921600)
        assert a.baud_rate != 921600
        assert b.baud_rate == 921600

    def test_apply_to_selected_skips_busy_device(self, controller):
        a = controller.add_device("A")
        controller.set_flash_controller(_FakeFlashController({a.id}))
        controller.apply_to_selected([a.id], "baud_rate", 230400)
        assert a.baud_rate != 230400

    def test_apply_firmware_to_devices_skips_busy_device_and_excludes_from_count(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        controller.set_flash_controller(_FakeFlashController({a.id}))
        updated = controller.apply_firmware_to_devices([a.id, b.id], self._entries())
        assert updated == 1
        assert a.firmware == []
        assert len(b.firmware) == 1

    def test_no_flash_controller_wired_means_no_guard(self, controller):
        """Backward compatible: with no FlashController wired in (e.g. a
        controller built without main_window's wiring), nothing is
        treated as busy."""
        a = controller.add_device("A")
        controller.apply_to_all("baud_rate", 921600)
        assert a.baud_rate == 921600


class TestFindDuplicatePorts:
    def test_no_duplicates_returns_empty(self, controller):
        controller.add_device("A").com_port = "COM3"
        controller.add_device("B").com_port = "COM4"
        assert controller.find_duplicate_ports() == {}

    def test_detects_duplicate_port_usage(self, controller):
        a = controller.add_device("A")
        a.com_port = "COM3"
        b = controller.add_device("B")
        b.com_port = "COM3"
        duplicates = controller.find_duplicate_ports()
        assert duplicates == {"COM3": ["A", "B"]}

    def test_devices_without_port_are_ignored(self, controller):
        controller.add_device("A")  # no com_port set
        controller.add_device("B")
        assert controller.find_duplicate_ports() == {}


class TestSearch:
    def test_empty_query_returns_all_devices(self, controller):
        controller.add_device("A")
        controller.add_device("B")
        assert len(controller.search("")) == 2
        assert len(controller.search("   ")) == 2

    def test_search_matches_name_case_insensitive(self, controller):
        controller.add_device("Bench One")
        controller.add_device("Bench Two")
        results = controller.search("one")
        assert [d.name for d in results] == ["Bench One"]

    def test_search_matches_port(self, controller):
        a = controller.add_device("A")
        a.com_port = "COM7"
        controller.add_device("B")
        results = controller.search("com7")
        assert results == [a]

    def test_search_matches_chip_type(self, controller):
        a = controller.add_device("A")
        a.chip_type = "esp32s3"
        results = controller.search("esp32s3")
        assert results == [a]

    def test_search_matches_tags(self, controller):
        a = controller.add_device("A")
        a.tags = ["Line X"]
        controller.add_device("B")
        results = controller.search("line x")
        assert results == [a]

    def test_search_no_match_returns_empty(self, controller):
        controller.add_device("A")
        assert controller.search("nonexistent-xyz") == []


class TestTags:
    def test_all_tags_sorted_and_deduplicated(self, controller):
        a = controller.add_device("A")
        a.tags = ["zebra", "apple"]
        b = controller.add_device("B")
        b.tags = ["apple", "mango"]
        assert controller.all_tags() == ["apple", "mango", "zebra"]

    def test_add_tag_to_devices(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        updated = controller.add_tag_to_devices([a.id, b.id], "Batch 7")
        assert updated == 2
        assert "Batch 7" in a.tags
        assert "Batch 7" in b.tags

    def test_add_tag_does_not_duplicate_existing_tag(self, controller):
        a = controller.add_device("A")
        a.tags = ["Batch 7"]
        controller.add_tag_to_devices([a.id], "Batch 7")
        assert a.tags.count("Batch 7") == 1

    def test_add_blank_tag_is_noop(self, controller):
        a = controller.add_device("A")
        updated = controller.add_tag_to_devices([a.id], "   ")
        assert updated == 0
        assert a.tags == []

    def test_add_tag_emits_device_updated(self, qtbot, controller):
        a = controller.add_device("A")
        with qtbot.waitSignal(controller.device_updated, timeout=1000):
            controller.add_tag_to_devices([a.id], "New Tag")


class TestSetProject:
    def test_set_project_replaces_devices_and_emits_reset(self, qtbot, controller):
        controller.add_device("Old Device")
        new_project = ProjectModel()
        new_project.add_device(DeviceConfig(name="New Device"))
        with qtbot.waitSignal(controller.devices_reset, timeout=1000):
            controller.set_project(new_project)
        assert [d.name for d in controller.devices()] == ["New Device"]


class TestUndoRedoIntegration:
    """DeviceController wires the four bulk mutation operations (Batch
    Edit, bulk removal, Assign Firmware Set, CSV import) through
    UndoStack -- see app/controllers/undo_stack.py."""

    def _entries(self):
        return [FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000")]

    def test_fresh_controller_cannot_undo_or_redo(self, controller):
        assert not controller.can_undo()
        assert not controller.can_redo()

    def test_apply_to_selected_is_undoable(self, controller):
        a = controller.add_device("A")
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        assert controller.get_device(a.id).baud_rate == 921600
        assert controller.can_undo()
        controller.undo()
        assert controller.get_device(a.id).baud_rate != 921600

    def test_apply_to_all_is_undoable(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        controller.apply_to_all("baud_rate", 460800)
        controller.undo()
        assert controller.get_device(a.id).baud_rate != 460800
        assert controller.get_device(b.id).baud_rate != 460800

    def test_apply_to_selected_with_only_unknown_ids_does_not_push_undo(self, controller):
        controller.add_device("A")
        # Neither an unknown device id nor an unknown field ever actually
        # touches a device, so no *additional* undo entry should be
        # recorded beyond the one add_device() itself already pushed.
        before = controller.undo_description()
        controller.apply_to_selected(["ghost-id"], "baud_rate", 1)
        assert controller.undo_description() == before

    def test_add_tag_to_devices_is_undoable(self, controller):
        a = controller.add_device("A")
        controller.add_tag_to_devices([a.id], "Batch 7")
        assert "Batch 7" in a.tags
        controller.undo()
        assert "Batch 7" not in controller.get_device(a.id).tags

    def test_add_tag_blank_does_not_push_undo(self, controller):
        controller.add_device("A")
        before = controller.undo_description()
        controller.add_tag_to_devices([controller.devices()[0].id], "   ")
        assert controller.undo_description() == before

    def test_apply_firmware_to_devices_is_undoable(self, controller):
        a = controller.add_device("A")
        controller.apply_firmware_to_devices([a.id], self._entries())
        assert len(controller.get_device(a.id).firmware) == 1
        controller.undo()
        assert controller.get_device(a.id).firmware == []

    def test_remove_devices_is_undoable(self, controller):
        a = controller.add_device("A")
        b = controller.add_device("B")
        removed = controller.remove_devices([a.id, b.id])
        assert removed == 2
        assert controller.devices() == []
        controller.undo()
        assert {d.name for d in controller.devices()} == {"A", "B"}

    def test_remove_devices_with_no_matches_does_not_push_undo(self, controller):
        controller.remove_devices(["ghost-id"])
        assert not controller.can_undo()

    def test_import_from_csv_is_undoable(self, controller, tmp_path):
        csv_path = tmp_path / "devices.csv"
        csv_path.write_text("name,com_port\nDevice A,COM3\n", encoding="utf-8")
        controller.import_from_csv(str(csv_path))
        assert len(controller.devices()) == 1
        controller.undo()
        assert controller.devices() == []

    def test_undo_then_redo_restores_mutation(self, controller):
        a = controller.add_device("A")
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        controller.undo()
        assert controller.get_device(a.id).baud_rate != 921600
        controller.redo()
        assert controller.get_device(a.id).baud_rate == 921600

    def test_new_mutation_after_undo_clears_redo(self, controller):
        a = controller.add_device("A")
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        controller.undo()
        assert controller.can_redo()
        controller.apply_to_selected([a.id], "baud_rate", 460800)
        assert not controller.can_redo()

    def test_undo_emits_undo_stack_changed_and_devices_reset(self, qtbot, controller):
        a = controller.add_device("A")
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        with qtbot.waitSignals([controller.undo_stack_changed, controller.devices_reset], timeout=1000):
            controller.undo()

    def test_undo_with_nothing_to_undo_returns_false(self, controller):
        assert controller.undo() is False

    def test_redo_with_nothing_to_redo_returns_false(self, controller):
        assert controller.redo() is False

    def test_set_project_clears_undo_history(self, controller):
        a = controller.add_device("A")
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        assert controller.can_undo()
        controller.set_project(ProjectModel())
        assert not controller.can_undo()
        assert not controller.can_redo()

    def test_undo_description_reflects_last_operation(self, controller):
        a = controller.add_device("A")
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        assert "Batch Edit" in controller.undo_description()

    def test_busy_device_mutation_that_changes_nothing_does_not_push_undo(self, controller):
        a = controller.add_device("A")
        controller.set_flash_controller(_FakeFlashController({a.id}))
        before = controller.undo_description()
        controller.apply_to_selected([a.id], "baud_rate", 921600)
        assert a.baud_rate != 921600
        assert controller.undo_description() == before

    def test_refresh_undo_stack_depth_applies_setting_live(self, controller):
        from app.utilities.app_settings import get_settings
        from app.utilities.constants import SETTINGS_KEY_UNDO_STACK_DEPTH

        for i in range(5):
            a = controller.add_device(f"A{i}")
            controller.apply_to_selected([a.id], "baud_rate", 921600 + i)

        get_settings().setValue(SETTINGS_KEY_UNDO_STACK_DEPTH, 2)
        controller.refresh_undo_stack_depth()

        count = 0
        while controller.can_undo():
            controller.undo()
            count += 1
        assert count == 2


class TestPreviewHelpers:
    """Read-only diff/preview helpers backing the Batch Edit and Assign
    Firmware Set confirmation dialogs -- see ROADMAP.md's "Diff / preview
    step" entry. These must never mutate project state."""

    def test_preview_field_change_reports_only_devices_that_would_change(self, controller):
        a = controller.add_device("A")
        a.baud_rate = 115200
        b = controller.add_device("B")
        b.baud_rate = 921600
        changes = controller.preview_field_change([a.id, b.id], "baud_rate", 921600)
        assert [c[0] for c in changes] == [a.id]
        assert changes[0][1] == "A"
        assert changes[0][2] == "115200"
        assert changes[0][3] == "921600"

    def test_preview_field_change_does_not_mutate(self, controller):
        a = controller.add_device("A")
        a.baud_rate = 115200
        controller.preview_field_change([a.id], "baud_rate", 921600)
        assert a.baud_rate == 115200

    def test_preview_field_change_skips_busy_devices(self, controller):
        a = controller.add_device("A")
        a.baud_rate = 115200
        controller.set_flash_controller(_FakeFlashController({a.id}))
        changes = controller.preview_field_change([a.id], "baud_rate", 921600)
        assert changes == []

    def test_preview_field_change_skips_unknown_field(self, controller):
        a = controller.add_device("A")
        changes = controller.preview_field_change([a.id], "not_a_real_field", 1)
        assert changes == []

    def test_preview_tag_addition_reports_new_tag(self, controller):
        a = controller.add_device("A")
        changes = controller.preview_tag_addition([a.id], "Batch 7")
        assert changes[0][2] == "(none)"
        assert changes[0][3] == "Batch 7"

    def test_preview_tag_addition_skips_devices_that_already_have_the_tag(self, controller):
        a = controller.add_device("A")
        a.tags = ["Batch 7"]
        changes = controller.preview_tag_addition([a.id], "Batch 7")
        assert changes == []

    def test_preview_tag_addition_blank_tag_returns_empty(self, controller):
        a = controller.add_device("A")
        assert controller.preview_tag_addition([a.id], "   ") == []

    def test_preview_firmware_assignment_reports_changed_devices(self, controller):
        a = controller.add_device("A")
        entries = [FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000")]
        changes = controller.preview_firmware_assignment([a.id], entries)
        assert changes[0][2] == "(none)"
        assert "firmware.bin@0x10000" in changes[0][3]

    def test_preview_firmware_assignment_skips_identical_assignment(self, controller):
        a = controller.add_device("A")
        entries = [FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000")]
        controller.apply_firmware_to_devices([a.id], entries)
        changes = controller.preview_firmware_assignment([a.id], entries)
        assert changes == []

    def test_preview_firmware_assignment_skips_busy_devices(self, controller):
        a = controller.add_device("A")
        controller.set_flash_controller(_FakeFlashController({a.id}))
        entries = [FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000")]
        assert controller.preview_firmware_assignment([a.id], entries) == []


class TestImportFromZipBundle:
    def _bundle(self, tmp_path):
        import zipfile

        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("manifest.csv", "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n")
            archive.writestr("firmware.bin", b"\x00" * 64)
        return str(zip_path)

    def test_import_adds_device_with_firmware_and_emits_signal(self, qtbot, controller, tmp_path):
        bundle = self._bundle(tmp_path)
        with qtbot.waitSignal(controller.device_added, timeout=1000):
            result = controller.import_from_zip_bundle(bundle)
        assert result.imported_count == 1
        device = controller.devices()[0]
        assert device.name == "Bench 1"
        assert len(device.firmware) == 1

    def test_import_is_undoable(self, controller, tmp_path):
        bundle = self._bundle(tmp_path)
        controller.import_from_zip_bundle(bundle)
        assert len(controller.devices()) == 1
        controller.undo()
        assert controller.devices() == []

    def test_import_error_propagates_as_exception(self, controller, tmp_path):
        from app.project_manager.zip_manifest_import import ZipManifestImportError

        with pytest.raises(ZipManifestImportError):
            controller.import_from_zip_bundle(str(tmp_path / "does_not_exist.zip"))


class TestPushDeviceEditUndo:
    """DeviceController.push_device_edit_undo -- the mechanism that makes
    single-device edits made directly by the Device Settings/Firmware/
    Security panels (which mutate their DeviceConfig in place) undoable,
    even though there's no DeviceController method call to wrap for
    those panels the way apply_to_selected() is wrapped."""

    def test_field_change_is_pushed_and_undoable(self, controller):
        a = controller.add_device("A")
        before = copy.deepcopy(a)
        a.name = "Renamed"

        pushed = controller.push_device_edit_undo(a.id, before, "Edit device settings")

        assert pushed is True
        assert controller.undo_description() == "Edit device settings"
        controller.undo()
        assert controller.get_device(a.id).name == "A"

    def test_no_actual_change_does_not_push(self, controller):
        a = controller.add_device("A")
        before = copy.deepcopy(a)
        # Nothing about `a` actually changed.
        baseline_description = controller.undo_description()

        pushed = controller.push_device_edit_undo(a.id, before, "Edit device settings")

        assert pushed is False
        assert controller.undo_description() == baseline_description

    def test_unknown_device_id_does_not_push(self, controller):
        a = controller.add_device("A")
        before = copy.deepcopy(a)
        pushed = controller.push_device_edit_undo("ghost-id", before, "Edit device settings")
        assert pushed is False

    def test_firmware_addition_is_undoable(self, controller):
        a = controller.add_device("A")
        before = copy.deepcopy(a)
        a.add_firmware(FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000"))

        controller.push_device_edit_undo(a.id, before, "Edit firmware")

        assert len(controller.get_device(a.id).firmware) == 1
        controller.undo()
        assert controller.get_device(a.id).firmware == []

    def test_redo_restores_the_edit(self, controller):
        a = controller.add_device("A")
        before = copy.deepcopy(a)
        a.name = "Renamed"
        controller.push_device_edit_undo(a.id, before, "Edit device settings")

        controller.undo()
        controller.redo()

        assert controller.get_device(a.id).name == "Renamed"


class TestAddRemoveDuplicateAreUndoable:
    """add_device/remove_device/duplicate_device must each push their own
    undo entry -- previously only the four *bulk* operations did."""

    def test_add_device_is_undoable(self, controller):
        controller.add_device("A")
        assert controller.can_undo()
        controller.undo()
        assert controller.devices() == []

    def test_remove_device_single_is_undoable(self, controller):
        a = controller.add_device("A")
        controller.remove_device(a.id)
        assert controller.devices() == []
        controller.undo()
        assert len(controller.devices()) == 1
        assert controller.devices()[0].name == "A"

    def test_remove_device_unknown_id_does_not_push(self, controller):
        controller.add_device("A")
        baseline = controller.undo_description()
        controller.remove_device("ghost-id")
        assert controller.undo_description() == baseline

    def test_duplicate_device_is_undoable(self, controller):
        controller.add_device("A")
        controller.duplicate_device(controller.devices()[0].id)
        assert len(controller.devices()) == 2
        controller.undo()
        assert len(controller.devices()) == 1

    def test_duplicate_unknown_device_does_not_push(self, controller):
        controller.add_device("A")
        baseline = controller.undo_description()
        result = controller.duplicate_device("ghost-id")
        assert result is None
        assert controller.undo_description() == baseline

    def test_add_then_remove_then_undo_twice_restores_original_state(self, controller):
        a = controller.add_device("A")
        controller.remove_device(a.id)
        assert controller.devices() == []
        controller.undo()  # undoes the remove
        assert len(controller.devices()) == 1
        controller.undo()  # undoes the add
        assert controller.devices() == []
