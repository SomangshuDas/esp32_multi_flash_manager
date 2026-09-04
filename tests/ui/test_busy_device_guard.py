"""
Tests confirming Batch Edit, Assign Firmware Set, and Firmware Profile
application all refuse to touch a device that's actively uploading (see
MainWindow._exclude_busy_devices and its call sites).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.firmware_manager.profiles import FirmwareProfile
from app.models.firmware_model import FirmwareEntry


class TestExcludeBusyDevices:
    def test_busy_device_is_excluded_and_named(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.flash_controller._workers[device.id] = MagicMock(isRunning=lambda: True)

        safe_ids, busy_names = window._exclude_busy_devices([device.id])

        assert safe_ids == []
        assert busy_names == ["Bench 1"]

    def test_idle_device_is_kept(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        safe_ids, busy_names = window._exclude_busy_devices([device.id])
        assert safe_ids == [device.id]
        assert busy_names == []

    def test_mixed_busy_and_idle_devices(self, main_window):
        window = main_window
        busy = window.device_controller.add_device("Busy Bench")
        idle = window.device_controller.add_device("Idle Bench")
        window.flash_controller._workers[busy.id] = MagicMock(isRunning=lambda: True)

        safe_ids, busy_names = window._exclude_busy_devices([busy.id, idle.id])

        assert safe_ids == [idle.id]
        assert busy_names == ["Busy Bench"]


class TestBatchEditRefusesBusyDevices:
    def test_apply_to_selected_never_called_for_busy_only_selection(self, main_window, monkeypatch):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.flash_controller._workers[device.id] = MagicMock(isRunning=lambda: True)

        applied = []
        monkeypatch.setattr(window.device_controller, "apply_to_selected", lambda ids, f, v: applied.append(ids))
        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [device.id])
        monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: None)

        class FakeDialog:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return True

            def selected_field(self):
                return "baud_rate"

            def selected_value(self):
                return 460800

            def apply_to_all(self):
                return False

        monkeypatch.setattr("app.ui.main_window.BatchEditDialog", FakeDialog)

        window._on_batch_edit()

        assert applied == []  # the only selected device was busy -- nothing applied

    def test_apply_to_selected_still_runs_for_the_idle_device_in_a_mixed_selection(self, main_window, monkeypatch):
        window = main_window
        busy = window.device_controller.add_device("Busy Bench")
        idle = window.device_controller.add_device("Idle Bench")
        window.flash_controller._workers[busy.id] = MagicMock(isRunning=lambda: True)

        applied = []
        monkeypatch.setattr(window.device_controller, "apply_to_selected", lambda ids, f, v: applied.append(ids))
        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [busy.id, idle.id])
        monkeypatch.setattr(window.device_panel, "rebuild", lambda devices: None)
        monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *a, **k: None)

        class FakeDialog:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return True

            def selected_field(self):
                return "baud_rate"

            def selected_value(self):
                return 460800

            def apply_to_all(self):
                return False

        monkeypatch.setattr("app.ui.main_window.BatchEditDialog", FakeDialog)

        window._on_batch_edit()

        assert applied == [[idle.id]]


class TestAssignFirmwareSetRefusesBusyDevices:
    def test_apply_firmware_never_called_for_busy_only_targets(self, main_window, monkeypatch):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.flash_controller._workers[device.id] = MagicMock(isRunning=lambda: True)

        applied = []
        monkeypatch.setattr(
            window.device_controller, "apply_firmware_to_devices",
            lambda ids, entries: applied.append(ids) or len(ids),
        )
        monkeypatch.setattr("app.ui.main_window.QFileDialog.getExistingDirectory", lambda *a, **k: "/tmp/fw")
        monkeypatch.setattr(
            "app.ui.main_window.scan_firmware_folder",
            lambda folder: [FirmwareEntry(file_path="/tmp/fw/firmware.bin", address="0x10000")],
        )
        monkeypatch.setattr(window, "_choose_assign_firmware_targets", lambda *a, **k: [device.id])
        monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *a, **k: None)

        window._on_assign_firmware_set()

        assert applied == []


class TestFirmwareProfileRefusesBusyDevice:
    def test_profile_dialog_never_opened_for_busy_device(self, main_window, monkeypatch):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.flash_controller._workers[device.id] = MagicMock(isRunning=lambda: True)

        opened = []
        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [device.id])
        monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
        monkeypatch.setattr(
            "app.ui.main_window.ProfileDialog",
            lambda *a, **k: opened.append(True),
        )

        window._on_open_profiles()

        assert opened == []

    def test_profile_dialog_opens_for_idle_device(self, main_window, monkeypatch):
        window = main_window
        device = window.device_controller.add_device("Bench 1")

        opened = []

        class FakeProfileDialog:
            def __init__(self, dev, parent):
                opened.append(dev.id)
                self.chosen_profile = None

            def exec(self):
                return False

        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [device.id])
        monkeypatch.setattr("app.ui.main_window.ProfileDialog", FakeProfileDialog)

        window._on_open_profiles()

        assert opened == [device.id]
