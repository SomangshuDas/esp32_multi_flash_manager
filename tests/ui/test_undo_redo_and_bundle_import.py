"""
Tests for MainWindow's Edit -> Undo/Redo wiring, Tools -> Validate Bench
(Dry Run)..., and Devices -> Import Firmware Bundle (.zip)... -- the
UI-level glue for the features implemented in
app/controllers/device_controller.py, app/flash_engine/validator.py, and
app/project_manager/zip_manifest_import.py (see ROADMAP.md).
"""

from __future__ import annotations

import zipfile

from PySide6.QtWidgets import QDialogButtonBox


class TestUndoRedoMenuWiring:
    def test_undo_redo_actions_start_disabled(self, main_window):
        window = main_window
        assert not window.undo_action.isEnabled()
        assert not window.redo_action.isEnabled()

    def test_undo_action_enabled_after_a_mutation(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.device_controller.apply_to_selected([device.id], "baud_rate", 921600)
        assert window.undo_action.isEnabled()
        assert not window.redo_action.isEnabled()

    def test_on_undo_triggers_controller_undo_and_rebuilds_panel(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.device_controller.apply_to_selected([device.id], "baud_rate", 921600)

        window._on_undo()

        assert window.device_controller.get_device(device.id).baud_rate != 921600
        # add_device() itself pushed its own undo entry, so one Ctrl+Z
        # undoes the Batch Edit but "Undo Add device..." is still available.
        assert window.undo_action.isEnabled()
        assert window.redo_action.isEnabled()

    def test_on_redo_triggers_controller_redo(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.device_controller.apply_to_selected([device.id], "baud_rate", 921600)
        window._on_undo()

        window._on_redo()

        assert window.device_controller.get_device(device.id).baud_rate == 921600

    def test_on_undo_with_nothing_to_undo_is_a_no_op(self, main_window):
        window = main_window
        window._on_undo()  # must not raise
        assert not window.undo_action.isEnabled()

    def test_undo_action_label_includes_operation_description(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window.device_controller.apply_to_selected([device.id], "baud_rate", 921600)
        assert "Batch Edit" in window.undo_action.text()


class TestValidateBenchDryRun:
    def test_no_devices_shows_info_message_not_a_dialog(self, main_window, monkeypatch):
        window = main_window
        shown = []
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: shown.append(a))
        window._on_validate_bench_dry_run()
        assert shown

    def test_runs_validation_and_opens_report_dialog(self, main_window, monkeypatch):
        window = main_window
        window.device_controller.add_device("Bench 1")

        opened = []

        class FakeDialog:
            def __init__(self, report, parent):
                opened.append(report)

            def exec(self):
                return False

        monkeypatch.setattr("app.ui.main_window.ValidationReportDialog", FakeDialog)
        window._on_validate_bench_dry_run()

        assert len(opened) == 1
        assert opened[0].dry_run is True

    def test_dry_run_does_not_require_a_connected_port(self, main_window, monkeypatch):
        """The whole point of a dry run: a device with a port that isn't
        currently plugged in must not show a blocking connectivity
        error."""
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        device.com_port = "COM99"  # never actually connected in this test

        opened = []
        monkeypatch.setattr(
            "app.ui.main_window.ValidationReportDialog",
            lambda report, parent: opened.append(report) or _FakeExec(),
        )
        window._on_validate_bench_dry_run()
        report = opened[0]
        assert not any("not currently connected" in i.message.lower() for i in report.issues)


class _FakeExec:
    def exec(self):
        return False


class TestImportFirmwareBundle:
    def _bundle(self, tmp_path):
        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("manifest.csv", "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n")
            archive.writestr("firmware.bin", b"\x00" * 64)
        return str(zip_path)

    def test_no_file_chosen_is_a_no_op(self, main_window, monkeypatch):
        window = main_window
        monkeypatch.setattr("app.ui.main_window.QFileDialog.getOpenFileName", lambda *a, **k: ("", ""))
        window._on_import_firmware_bundle()
        assert window.device_controller.devices() == []

    def test_successful_import_adds_device_and_shows_summary(self, main_window, monkeypatch, tmp_path):
        window = main_window
        bundle = self._bundle(tmp_path)
        monkeypatch.setattr("app.ui.main_window.QFileDialog.getOpenFileName", lambda *a, **k: (bundle, ""))
        shown = []
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: shown.append(a))

        window._on_import_firmware_bundle()

        assert len(window.device_controller.devices()) == 1
        assert window.device_controller.devices()[0].name == "Bench 1"
        assert shown

    def test_archive_level_error_shows_warning_not_a_crash(self, main_window, monkeypatch, tmp_path):
        window = main_window
        bad_zip = tmp_path / "not_a_zip.zip"
        bad_zip.write_text("nope")
        monkeypatch.setattr("app.ui.main_window.QFileDialog.getOpenFileName", lambda *a, **k: (str(bad_zip), ""))
        warned = []
        monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *a, **k: warned.append(a))

        window._on_import_firmware_bundle()

        assert warned
        assert window.device_controller.devices() == []


class _FakeBatchEditDialog:
    def __init__(self, field, value, apply_to_all=False):
        self._field = field
        self._value = value
        self._apply_to_all = apply_to_all

    def __call__(self, *a, **k):
        return self

    def exec(self):
        return True

    def selected_field(self):
        return self._field

    def selected_value(self):
        return self._value

    def apply_to_all(self):
        return self._apply_to_all


class _FakePreviewDialog:
    last_changes = None

    def __init__(self, title, changes, parent=None):
        type(self).last_changes = changes

    def exec(self):
        return self.DialogCode.Accepted

    class DialogCode:
        Accepted = 1
        Rejected = 0


class _FakeRejectedPreviewDialog(_FakePreviewDialog):
    def exec(self):
        return self.DialogCode.Rejected


class TestBatchEditDiffPreview:
    def test_preview_dialog_receives_only_actually_changed_devices(self, main_window, monkeypatch):
        window = main_window
        a = window.device_controller.add_device("A")
        a.baud_rate = 115200
        b = window.device_controller.add_device("B")
        b.baud_rate = 921600  # already at the target value -- should not appear

        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [a.id, b.id])
        monkeypatch.setattr(
            "app.ui.main_window.BatchEditDialog", _FakeBatchEditDialog("baud_rate", 921600),
        )
        monkeypatch.setattr("app.ui.main_window.ChangePreviewDialog", _FakePreviewDialog)

        window._on_batch_edit()

        assert [c[0] for c in _FakePreviewDialog.last_changes] == [a.id]
        assert window.device_controller.get_device(a.id).baud_rate == 921600

    def test_cancelling_preview_dialog_applies_nothing(self, main_window, monkeypatch):
        window = main_window
        a = window.device_controller.add_device("A")
        a.baud_rate = 115200

        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [a.id])
        monkeypatch.setattr(
            "app.ui.main_window.BatchEditDialog", _FakeBatchEditDialog("baud_rate", 921600),
        )
        monkeypatch.setattr("app.ui.main_window.ChangePreviewDialog", _FakeRejectedPreviewDialog)

        window._on_batch_edit()

        assert window.device_controller.get_device(a.id).baud_rate == 115200
        # Only add_device()'s own undo entry should exist -- the cancelled
        # Batch Edit must not have pushed a second one.
        assert window.device_controller.undo_description() == "Add device 'A'"

    def test_no_actual_changes_skips_preview_dialog_entirely(self, main_window, monkeypatch):
        window = main_window
        a = window.device_controller.add_device("A")
        a.baud_rate = 921600  # already at the target value

        monkeypatch.setattr(window.device_panel, "selected_device_ids", lambda: [a.id])
        monkeypatch.setattr(
            "app.ui.main_window.BatchEditDialog", _FakeBatchEditDialog("baud_rate", 921600),
        )
        opened = []
        monkeypatch.setattr(
            "app.ui.main_window.ChangePreviewDialog", lambda *a, **k: opened.append(True),
        )
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: None)

        window._on_batch_edit()

        assert opened == []


class TestUndoDepthSetting:
    def test_undo_depth_spin_defaults_to_constant(self, main_window):
        from app.ui.settings_dialog import SettingsDialog
        from app.utilities.constants import UNDO_STACK_DEPTH

        dialog = SettingsDialog(main_window)
        assert dialog.undo_depth_spin.value() == UNDO_STACK_DEPTH
        dialog.close()

    def test_saving_undo_depth_persists_and_applies_live(self, main_window):
        from app.ui.settings_dialog import SettingsDialog
        from app.utilities.app_settings import get_undo_stack_depth

        dialog = SettingsDialog(main_window)
        dialog.undo_depth_spin.setValue(7)
        dialog.save()
        dialog.close()

        assert get_undo_stack_depth() == 7

        main_window.device_controller.refresh_undo_stack_depth()
        assert main_window.device_controller.undo_stack.max_depth == 7

    def test_spin_box_is_clamped_to_configured_range(self, main_window):
        from app.ui.settings_dialog import SettingsDialog
        from app.utilities.constants import UNDO_STACK_DEPTH_MAX, UNDO_STACK_DEPTH_MIN

        dialog = SettingsDialog(main_window)
        assert dialog.undo_depth_spin.minimum() == UNDO_STACK_DEPTH_MIN
        assert dialog.undo_depth_spin.maximum() == UNDO_STACK_DEPTH_MAX
        dialog.close()


class TestPerDeviceEditUndoTracking:
    """Rename / any Device Settings field / Firmware Additions / Security
    changes made through the per-device panels (not Batch Edit) must be
    undoable too -- previously only the four bulk operations were."""

    def test_selecting_a_device_captures_a_baseline(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)
        assert window._pre_edit_snapshot_device_id == device.id
        assert window._pre_edit_snapshot.name == "Bench 1"

    def test_rename_via_settings_widget_commit_is_undoable(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)

        device.name = "Renamed Bench"
        window._push_device_edit_undo(device.id, "Edit device settings")

        assert window.device_controller.undo_description() == "Edit device settings"
        window.device_controller.undo()
        assert window.device_controller.get_device(device.id).name == "Bench 1"

    def test_firmware_addition_via_panel_commit_is_undoable(self, main_window):
        from app.models.firmware_model import FirmwareEntry

        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)

        device.add_firmware(FirmwareEntry(file_path="/tmp/firmware.bin", address="0x10000"))
        window._push_device_edit_undo(device.id, "Edit firmware")

        assert len(window.device_controller.get_device(device.id).firmware) == 1
        window.device_controller.undo()
        assert window.device_controller.get_device(device.id).firmware == []

    def test_security_change_via_panel_commit_is_undoable(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)

        device.security.enable_flash_encryption = True
        window._push_device_edit_undo(device.id, "Edit device security")

        assert window.device_controller.get_device(device.id).security.enable_flash_encryption is True
        window.device_controller.undo()
        assert window.device_controller.get_device(device.id).security.enable_flash_encryption is False

    def test_committing_with_no_actual_change_does_not_push_undo(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)
        baseline = window.device_controller.undo_description()

        # editingFinished can fire without the value having changed.
        window._push_device_edit_undo(device.id, "Edit device settings")

        assert window.device_controller.undo_description() == baseline

    def test_two_separate_commits_produce_two_separate_undo_steps(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)

        device.name = "First Rename"
        window._push_device_edit_undo(device.id, "Edit device settings")
        device.baud_rate = 921600
        window._push_device_edit_undo(device.id, "Edit device settings")

        window.device_controller.undo()  # undoes the baud rate change only
        assert window.device_controller.get_device(device.id).name == "First Rename"
        assert window.device_controller.get_device(device.id).baud_rate != 921600

    def test_signal_wiring_pushes_undo_on_real_settings_changed_signal(self, main_window):
        """End-to-end: emitting settings_widget.settings_changed (as the
        real widget does after editingFinished) must reach the undo
        stack via the lambda wired up in _wire_signals."""
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_selected(device.id)

        device.name = "Renamed via signal"
        window.settings_widget.settings_changed.emit(device.id)

        assert window.device_controller.can_undo()
        assert "Edit device settings" in window.device_controller.undo_description()


class TestMenuOrder:
    def test_edit_menu_immediately_follows_file_menu(self, main_window):
        menu_bar = main_window.menuBar()
        titles = [action.text().replace("&", "") for action in menu_bar.actions()]
        assert titles.index("Edit") == titles.index("File") + 1


class TestSettingsGeneralTabNoDuplicateLogsButton:
    def test_general_tab_has_no_open_logs_folder_button(self, main_window):
        from PySide6.QtWidgets import QPushButton, QTabWidget

        from app.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(main_window)
        tabs = dialog.findChild(QTabWidget)
        general_tab = tabs.widget(tabs.indexOf(tabs.widget(0)))
        assert tabs.tabText(0) == "General"
        buttons = general_tab.findChildren(QPushButton)
        assert not any(b.text() == "Open Logs Folder" for b in buttons)
        dialog.close()

    def test_diagnostics_tab_still_has_open_logs_folder_button(self, main_window):
        from PySide6.QtWidgets import QPushButton, QTabWidget

        from app.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(main_window)
        tabs = dialog.findChild(QTabWidget)
        diagnostics_index = None
        for i in range(tabs.count()):
            if tabs.tabText(i) == "Diagnostics":
                diagnostics_index = i
                break
        assert diagnostics_index is not None
        diagnostics_tab = tabs.widget(diagnostics_index)
        buttons = diagnostics_tab.findChildren(QPushButton)
        assert any(b.text() == "Open Logs Folder" for b in buttons)
        dialog.close()
