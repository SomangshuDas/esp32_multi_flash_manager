"""
pytest-qt integration tests for app/controllers/device_controller.py.

These exercise the controller against a real ProjectModel and rely on
pytest-qt's `qtbot` fixture to assert Qt signals actually fire, since
DeviceController is a QObject and the UI depends on those signals for
live updates.
"""

from __future__ import annotations

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
