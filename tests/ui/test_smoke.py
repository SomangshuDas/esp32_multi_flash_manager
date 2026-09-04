"""
Headless UI smoke tests (QT_QPA_PLATFORM=offscreen, set globally in
tests/conftest.py). These don't assert detailed behavior -- just that
the main window and every panel/dialog can be built and interacted with
at a basic level without raising.
"""

from __future__ import annotations

from app.ui.batch_edit_dialog import BatchEditDialog
from app.ui.merge_bin_dialog import MergeBinDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.shortcuts_dialog import ShortcutsDialog


class TestMainWindowBuilds:
    def test_main_window_constructs_without_raising(self, main_window):
        assert main_window is not None

    def test_main_window_has_all_expected_panels(self, main_window):
        window = main_window
        assert window.device_panel is not None
        assert window.firmware_panel is not None
        assert window.settings_widget is not None
        assert window.security_widget is not None
        assert window.history_panel is not None
        assert window.dashboard is not None

    def test_window_title_is_set(self, main_window):
        assert main_window.windowTitle()

    def test_menu_bar_has_menus(self, main_window):
        menu_bar = main_window.menuBar()
        assert len(menu_bar.actions()) > 0


class TestPanelsOpenWithoutExceptions:
    def test_add_device_updates_table(self, qtbot, main_window):
        window = main_window
        window._on_add_device()
        assert len(window.device_controller.devices()) == 1

    def test_selecting_a_device_populates_firmware_and_settings_panels(self, main_window):
        window = main_window
        device = window.device_controller.add_device("Bench 1")
        window._on_device_added(device.id)
        window._on_device_selected(device.id)
        assert window.firmware_panel._device is device
        assert window.settings_widget.current_device_id() == device.id

    def test_dashboard_refresh_does_not_raise(self, main_window):
        main_window.device_controller.add_device("Bench 1")
        main_window._refresh_dashboard()

    def test_search_and_tag_filter_do_not_raise(self, main_window):
        window = main_window
        window.device_controller.add_device("Bench 1")
        window._on_search_changed("bench")
        window._on_tag_filter_changed("")

    def test_sort_mode_change_does_not_raise(self, main_window):
        window = main_window
        window.device_controller.add_device("B")
        window.device_controller.add_device("A")
        from app.utilities.constants import DEVICE_SORT_NAME, DEVICE_SORT_TAG

        window._on_sort_mode_changed(DEVICE_SORT_NAME)
        window._on_sort_mode_changed(DEVICE_SORT_TAG)

    def test_history_panel_can_display_entries(self, main_window):
        from app.models.history_model import HistoryEntry

        entry = HistoryEntry.create(
            device_name="Bench 1", com_port="COM3", firmware_summary="fw.bin", duration_seconds=1.0, result="Completed",
        )
        main_window.history_panel.add_entry(entry)


class TestDialogsOpenWithoutExceptions:
    def test_batch_edit_dialog_builds(self, qtbot, main_window):
        dialog = BatchEditDialog(2, main_window, supported_chips=["esp32", "esp32s3"])
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_shortcuts_dialog_builds(self, qtbot, main_window):
        dialog = ShortcutsDialog(main_window)
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_settings_dialog_builds(self, qtbot, main_window):
        dialog = SettingsDialog(main_window)
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_merge_bin_dialog_builds(self, qtbot, main_window, tmp_path):
        from app.models.device_model import DeviceConfig
        from app.models.firmware_model import FirmwareEntry

        device = DeviceConfig(name="Bench 1", chip_type="esp32")
        firmware_path = tmp_path / "firmware.bin"
        firmware_path.write_bytes(b"\x00" * 16)
        device.add_firmware(FirmwareEntry(file_path=str(firmware_path), address="0x10000"))
        dialog = MergeBinDialog(device, ["esp32", "esp32s3"], main_window)
        qtbot.addWidget(dialog)
        assert dialog is not None


class TestNoUncaughtExceptionsDuringNormalFlow:
    def test_add_remove_duplicate_cycle_does_not_raise(self, main_window):
        window = main_window
        window._on_add_device()
        device_id = window.device_controller.devices()[0].id
        window._on_duplicate_devices([device_id])
        assert len(window.device_controller.devices()) == 2

    def test_closing_with_no_unsaved_changes_does_not_prompt(self, main_window):
        """A close with nothing dirty and nothing busy must accept
        immediately -- no real, blocking confirmation dialog."""
        window = main_window
        assert window.project_controller.dirty is False
        assert window.close() is True
