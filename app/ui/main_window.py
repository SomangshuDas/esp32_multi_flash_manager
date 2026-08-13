"""
main_window.py
===============
The application's top-level QMainWindow. Responsible for:

  - Menu bar / toolbar / status bar / keyboard shortcuts
  - Docking layout (Device List, Firmware+Settings, Dashboard, History)
  - Wiring DeviceController / FlashController / ProjectController signals
    to the relevant panels
  - Project lifecycle (new/open/save/save-as) with unsaved-changes checks
  - Live console window management (one per device, created on demand)
  - Theme switching and persistent window layout via AppSettings

This module intentionally contains no flashing logic and no file-format
logic itself — it delegates to the controllers/managers and only handles
wiring + user interaction.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTabWidget,
    QToolBar,
    QWidget,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from app.controllers.device_controller import DeviceController
from app.controllers.flash_controller import FlashController
from app.controllers.project_controller import ProjectController
from app.flash_engine.validator import validate_devices
from app.logging_setup.logger import get_logger
from app.project_manager.project_io import clear_recent_projects, get_recent_projects
from app.ui.batch_edit_dialog import BatchEditDialog
from app.ui.dashboard import DashboardWidget
from app.ui.device_panel import DevicePanel
from app.ui.device_settings_widget import DeviceSettingsWidget
from app.ui.firmware_panel import FirmwarePanel
from app.ui.history_panel import HistoryPanel
from app.ui.live_console import LiveConsoleWidget
from app.ui.profile_dialog import ProfileDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import stylesheet_for
from app.ui.validation_dialog import ValidationReportDialog
from app.utilities.app_settings import get_settings
from app.utilities.constants import APP_NAME, APP_VERSION, LIVE_LOG_MAX_LINES, PROJECT_FILE_FILTER
from app.utilities.helpers import resource_path, safe_filename
from app.utilities.update_checker import check_for_update
from app.workers.port_watcher import PortWatcher

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1400, 860)
        self.setWindowIcon(self._load_window_icon())

        self.settings = get_settings()

        # ---------------- Controllers ----------------
        self.project_controller = ProjectController(self)
        self.device_controller = DeviceController(self.project_controller.project, self)
        self.flash_controller = FlashController(self)
        self.port_watcher = PortWatcher(self)

        self._live_consoles: dict[str, LiveConsoleWidget] = {}
        self._device_log_buffers: dict[str, list[str]] = {}
        self._connected_ports: set[str] = set()
        self._had_saved_geometry = False

        self._build_ui()
        self._build_menus_and_toolbar()
        self._wire_signals()
        self._apply_theme(self.settings.value("theme", "dark"))

        self.port_watcher.start()
        self._refresh_dashboard()
        self._restore_window_layout()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)

        self.dashboard = DashboardWidget()
        central_layout.addWidget(self.dashboard)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.device_panel = DevicePanel()
        splitter.addWidget(self.device_panel)

        right_tabs = QTabWidget()
        self.firmware_panel = FirmwarePanel()
        self.settings_widget = DeviceSettingsWidget()
        right_tabs.addTab(self.firmware_panel, "Firmware")
        right_tabs.addTab(self.settings_widget, "Device Settings")
        splitter.addWidget(right_tabs)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        central_layout.addWidget(splitter, 1)

        self.setCentralWidget(central)

        # History dock
        self.history_panel = HistoryPanel()
        history_dock = QDockWidget("Flash History", self)
        history_dock.setObjectName("historyDock")
        history_dock.setWidget(self.history_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, history_dock)
        self.history_dock = history_dock
        # Off by default for a cleaner first-run layout; a returning user's
        # last-saved state (restored afterwards in _restore_window_layout)
        # still takes precedence if they'd previously left it open.
        history_dock.setVisible(False)

        # Status bar with overall progress
        self.overall_progress = QProgressBar()
        self.overall_progress.setMaximumWidth(220)
        self.overall_progress.setFormat("Overall: %p%")
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.overall_progress)

    def _build_menus_and_toolbar(self) -> None:
        menu_bar = self.menuBar()

        # ---- File menu ----
        file_menu = menu_bar.addMenu("&File")
        self._add_action(file_menu, "&New Project", "Ctrl+N", self._on_new_project)
        self._add_action(file_menu, "&Open Project...", "Ctrl+O", self._on_open_project)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Project", "Ctrl+S", self._on_save_project)
        self._add_action(file_menu, "Save Project &As...", "Ctrl+Shift+S", self._on_save_project_as)
        self._add_action(file_menu, "Rena&me Project...", "", self._on_rename_project)
        file_menu.addSeparator()
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_menu()
        file_menu.addSeparator()
        self._add_action(file_menu, "E&xit", "Ctrl+Q", self.close)

        # ---- Devices menu ----
        devices_menu = menu_bar.addMenu("&Devices")
        self._add_action(devices_menu, "Add Device", "Ctrl+D", self.device_panel.add_device_requested.emit)
        self._add_action(devices_menu, "Batch Edit...", "Ctrl+B", self._on_batch_edit)
        self._add_action(devices_menu, "Firmware Profiles...", "", self._on_open_profiles)

        # ---- Flash menu ----
        flash_menu = menu_bar.addMenu("&Flash")
        self._add_action(flash_menu, "Upload Selected", "F5", self._on_upload_selected)
        self._add_action(flash_menu, "Upload All", "Ctrl+F5", self._on_upload_all)
        self._add_action(flash_menu, "Cancel Selected", "", self._on_cancel_selected)
        self._add_action(flash_menu, "Cancel All", "Esc", self._on_cancel_all)
        self._add_action(flash_menu, "Retry Failed", "", self._on_retry_failed)
        self._add_action(flash_menu, "Retry Selected", "", self._on_retry_selected)

        # ---- View menu ----
        view_menu = menu_bar.addMenu("&View")
        self._add_action(view_menu, "Toggle Dark/Light Theme", "Ctrl+T", self._toggle_theme)
        view_menu.addAction(self.history_dock.toggleViewAction())

        # ---- Tools menu ----
        tools_menu = menu_bar.addMenu("&Tools")
        self._add_action(tools_menu, "Settings...", "", self._on_open_settings)
        self._add_action(tools_menu, "Check for Updates...", "", self._on_check_updates)

        # ---- Help menu ----
        help_menu = menu_bar.addMenu("&Help")
        self._add_action(help_menu, "About", "", self._on_about)

        # ---- Toolbar ----
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self._add_action(toolbar, "Upload Selected", "", self._on_upload_selected)
        self._add_action(toolbar, "Upload All", "", self._on_upload_all)
        self._add_action(toolbar, "Cancel Selected", "", self._on_cancel_selected)
        self._add_action(toolbar, "Cancel All", "", self._on_cancel_all)
        self._add_action(toolbar, "Retry Failed", "", self._on_retry_failed)
        self.addToolBar(toolbar)

    def _add_action(self, target, text: str, shortcut: str, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        target.addAction(action)
        return action

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _wire_signals(self) -> None:
        # Device panel <-> device controller
        self.device_panel.add_device_requested.connect(self._on_add_device)
        self.device_panel.remove_devices_requested.connect(self._on_remove_devices)
        self.device_panel.duplicate_devices_requested.connect(self._on_duplicate_devices)
        self.device_panel.selection_changed.connect(self._on_device_selected)
        self.device_panel.view_log_requested.connect(self._on_view_log)
        self.device_panel.upload_requested.connect(self._upload_device_ids)
        self.device_panel.cancel_requested.connect(self._cancel_device_ids)
        self.device_panel.search_box.textChanged.connect(self._on_search_changed)

        self.device_controller.device_added.connect(self._on_device_added)
        self.device_controller.device_removed.connect(self.device_panel.remove_device_row)
        self.device_controller.device_updated.connect(self._on_device_updated)
        self.device_controller.devices_reset.connect(self._on_devices_reset)

        self.firmware_panel.firmware_changed.connect(self._on_device_config_changed)
        self.settings_widget.settings_changed.connect(self._on_device_config_changed)

        # Flash controller -> device panel + history
        self.flash_controller.device_status_changed.connect(self._on_status_changed)
        self.flash_controller.device_progress_changed.connect(self._on_device_progress)
        self.flash_controller.device_speed_changed.connect(self.device_panel.set_speed)
        self.flash_controller.device_log_line.connect(self._on_log_line)
        self.flash_controller.batch_finished.connect(self._on_batch_finished)
        self.flash_controller.history_entry_created.connect(self.history_panel.add_entry)

        # Project controller
        self.project_controller.project_loaded.connect(self._on_project_loaded)
        self.project_controller.project_saved.connect(self._on_project_saved)
        self.project_controller.missing_firmware_detected.connect(self._on_missing_firmware)
        self.project_controller.load_failed.connect(self._on_load_failed)

        # Port watcher
        self.port_watcher.ports_changed.connect(self._on_ports_changed)
        self.port_watcher.port_connected.connect(lambda name: self.statusBar().showMessage(f"Device connected: {name}", 3000))
        self.port_watcher.port_disconnected.connect(lambda name: self.statusBar().showMessage(f"Device disconnected: {name}", 3000))

    # ------------------------------------------------------------------
    # Device list <-> controller glue
    # ------------------------------------------------------------------
    def _on_add_device(self) -> None:
        self.device_controller.add_device()

    def _on_device_added(self, device_id: str) -> None:
        self.device_panel.rebuild(self.device_controller.devices())
        self.project_controller.mark_dirty()
        self._refresh_dashboard()

    def _on_remove_devices(self, device_ids: list[str]) -> None:
        confirm = QMessageBox.question(self, "Remove Devices", f"Remove {len(device_ids)} device(s)?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for device_id in device_ids:
            self.device_controller.remove_device(device_id)
        self.project_controller.mark_dirty()
        self._refresh_dashboard()

    def _on_duplicate_devices(self, device_ids: list[str]) -> None:
        for device_id in device_ids:
            self.device_controller.duplicate_device(device_id)
        self.device_panel.rebuild(self.device_controller.devices())
        self.project_controller.mark_dirty()

    def _on_device_selected(self, device_id: str | None) -> None:
        device = self.device_controller.get_device(device_id) if device_id else None
        self.firmware_panel.set_device(device)
        self.settings_widget.set_device(device)

    def _on_device_config_changed(self, device_id: str) -> None:
        device = self.device_controller.get_device(device_id)
        if device:
            self.device_panel.update_device_summary(device)
        self.project_controller.mark_dirty()

    def _on_device_updated(self, device_id: str) -> None:
        device = self.device_controller.get_device(device_id)
        if device:
            self.device_panel.update_device_summary(device)

    def _on_devices_reset(self) -> None:
        self.device_panel.rebuild(self.device_controller.devices())
        self._refresh_dashboard()

    def _on_search_changed(self, text: str) -> None:
        if not text.strip():
            self.device_panel.apply_search_filter(None)
            return
        visible = {d.id for d in self.device_controller.search(text)}
        self.device_panel.apply_search_filter(visible)

    # ------------------------------------------------------------------
    # Firmware profiles
    # ------------------------------------------------------------------
    def _on_open_profiles(self) -> None:
        device_id = self.device_panel.selected_device_ids()
        device = self.device_controller.get_device(device_id[0]) if device_id else None
        if device is None:
            QMessageBox.information(self, "Firmware Profiles", "Select a device first.")
            return
        dialog = ProfileDialog(device, self)
        if dialog.exec() and dialog.chosen_profile is not None:
            dialog.chosen_profile.apply_to_device(device)
            self.firmware_panel.set_device(device)
            self.settings_widget.set_device(device)
            self.device_panel.update_device_summary(device)
            self.project_controller.mark_dirty()

    def _on_batch_edit(self) -> None:
        selected_ids = self.device_panel.selected_device_ids()
        dialog = BatchEditDialog(len(selected_ids), self)
        if dialog.exec():
            field = dialog.selected_field()
            value = dialog.selected_value()
            if dialog.apply_to_all():
                self.device_controller.apply_to_all(field, value)
            else:
                if not selected_ids:
                    QMessageBox.information(self, "Batch Edit", "No devices selected.")
                    return
                self.device_controller.apply_to_selected(selected_ids, field, value)
            self.device_panel.rebuild(self.device_controller.devices())
            selected = self.device_panel.selected_device_ids()
            if selected:
                self._on_device_selected(selected[0])
            self.project_controller.mark_dirty()

    # ------------------------------------------------------------------
    # Flashing actions
    # ------------------------------------------------------------------
    def _on_upload_selected(self) -> None:
        ids = self.device_panel.selected_device_ids()
        if not ids:
            QMessageBox.information(self, "Upload Selected", "Select at least one device first.")
            return
        self._upload_device_ids(ids)

    def _on_upload_all(self) -> None:
        self._upload_device_ids([d.id for d in self.device_controller.devices()])

    def _upload_device_ids(self, device_ids: list[str]) -> None:
        devices = [self.device_controller.get_device(did) for did in device_ids]
        devices = [d for d in devices if d is not None]
        if not devices:
            return

        report = validate_devices(devices, self._connected_ports)
        if report.has_errors:
            ValidationReportDialog(report, self).exec()
            return
        if report.has_warnings:
            dialog = ValidationReportDialog(report, self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                return

        for device in devices:
            self.device_panel.reset_progress(device.id)
            self._device_log_buffers[device.id] = []
            console = self._live_consoles.get(device.id)
            if console is not None:
                # Only reset an already-open console (the user opened it
                # themselves at some point); never open a new one here.
                # Progress is shown per-device in the main table by default
                # so non-technical users aren't confronted with extra
                # console windows they didn't ask for. "View Log" on a row
                # still opens/reuses a console on demand, fully populated
                # via the buffered history below.
                console.start_new_run()

        self.overall_progress.setValue(0)
        self.status_label.setText(f"Uploading {len(devices)} device(s)...")
        self.flash_controller.start_batch(devices)

    def _on_cancel_selected(self) -> None:
        self._cancel_device_ids(self.device_panel.selected_device_ids())

    def _on_cancel_all(self) -> None:
        self.flash_controller.cancel_all()

    def _cancel_device_ids(self, device_ids: list[str]) -> None:
        for device_id in device_ids:
            self.flash_controller.cancel(device_id)

    def _on_retry_failed(self) -> None:
        from app.utilities.constants import STATUS_FAILED
        failed = [d for d in self.device_controller.devices() if d.runtime.status == STATUS_FAILED]
        if not failed:
            QMessageBox.information(self, "Retry Failed", "No failed devices to retry.")
            return
        self._upload_device_ids([d.id for d in failed])

    def _on_retry_selected(self) -> None:
        ids = self.device_panel.selected_device_ids()
        if ids:
            self._upload_device_ids(ids)

    def _on_status_changed(self, device_id: str, status: str) -> None:
        self.device_panel.set_status(device_id, status)
        device = self.device_controller.get_device(device_id)
        if device:
            device.runtime.status = status
        console = self._live_consoles.get(device_id)
        if console is not None:
            console.set_status(status)
        self._refresh_dashboard()

    def _on_device_progress(self, device_id: str, percent: int, address: str) -> None:
        self.device_panel.set_progress(device_id, percent, address)
        console = self._live_consoles.get(device_id)
        if console is not None:
            console.set_progress(percent, address)

    def _on_log_line(self, device_id: str, line: str) -> None:
        # Buffer every line regardless of whether the live console window is
        # currently open, so opening it later (or re-opening after it was
        # closed) always replays full history instead of appearing blank.
        buffer = self._device_log_buffers.setdefault(device_id, [])
        buffer.append(line)
        if len(buffer) > LIVE_LOG_MAX_LINES:
            del buffer[: len(buffer) - LIVE_LOG_MAX_LINES]
        console = self._live_consoles.get(device_id)
        if console is not None:
            console.append_line(line)

    def _on_batch_finished(self, succeeded: int, failed: int) -> None:
        self.overall_progress.setValue(100)
        self.status_label.setText(f"Batch finished: {succeeded} succeeded, {failed} failed.")
        self._refresh_dashboard()

    def _on_view_log(self, device_id: str) -> None:
        self._open_live_console(device_id, focus=True)

    def _open_live_console(self, device_id: str, focus: bool = True) -> LiveConsoleWidget | None:
        """
        Get-or-create the live console for `device_id`, replaying any
        buffered log lines and current status/progress so it never opens
        blank — even if flashing already started before the window existed.
        """
        device = self.device_controller.get_device(device_id)
        if device is None:
            return None
        console = self._live_consoles.get(device_id)
        if console is None:
            console = LiveConsoleWidget(device.name)
            for line in self._device_log_buffers.get(device_id, []):
                console.append_line(line)
            console.set_status(device.runtime.status)
            self._live_consoles[device_id] = console
        console.show()
        if focus:
            console.raise_()
            console.activateWindow()
        return console

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------
    def _confirm_discard_changes(self) -> bool:
        if not self.project_controller.dirty:
            return True
        result = QMessageBox.question(
            self, "Unsaved Changes",
            "The current project has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _on_new_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        self.project_controller.new_project()

    def _on_open_project(self, file_path: str | None = None) -> None:
        if not self._confirm_discard_changes():
            return
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Open Project", "", PROJECT_FILE_FILTER,
                options=QFileDialog.Option.DontUseNativeDialog,
            )
        if not file_path:
            return
        self.project_controller.open_project(file_path)

    def open_project_at_startup(self, file_path: str) -> None:
        """
        Open `file_path` right after the window is constructed, bypassing the
        unsaved-changes prompt (there is nothing to discard yet). Used when the
        app is launched by double-clicking a .efmproj file — either passed as
        a command-line argument (Windows/Linux file association) or delivered
        via a macOS QFileOpenEvent. Any failure is reported the same way a
        manual File -> Open would report it, never a silent no-op.
        """
        logger.info("Opening project from startup file association: %s", file_path)
        self.project_controller.open_project(file_path)

    def _on_save_project(self) -> None:
        if self.project_controller.current_file_path is None:
            self._on_save_project_as()
            return
        self.project_controller.save_project()

    def _on_save_project_as(self) -> None:
        project = self.project_controller.project
        default_stem = safe_filename(project.project_name) if project.project_name else "project"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", f"{default_stem}.efmproj", PROJECT_FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not file_path:
            return

        # Let the user set a custom project name alongside the file name,
        # pre-filled from the chosen file so "Untitled Project" never
        # silently sticks around after a Save As.
        suggested_name = Path(file_path).stem
        name, ok = QInputDialog.getText(
            self, "Project Name", "Project name:", QLineEdit.EchoMode.Normal, suggested_name,
        )
        project.project_name = name.strip() if ok and name.strip() else suggested_name

        self.project_controller.save_project(file_path)

    def _on_rename_project(self) -> None:
        project = self.project_controller.project
        name, ok = QInputDialog.getText(
            self, "Rename Project", "Project name:", QLineEdit.EchoMode.Normal, project.project_name,
        )
        if not ok or not name.strip():
            return
        project.project_name = name.strip()
        self.project_controller.mark_dirty()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — {project.project_name}")
        self.statusBar().showMessage("Project renamed.", 3000)

    def _on_project_loaded(self, project) -> None:
        self.device_controller.set_project(project)
        self._live_consoles.clear()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — {project.project_name}")
        self._refresh_recent_menu()

    def _on_project_saved(self, file_path: str) -> None:
        self.statusBar().showMessage(f"Project saved to {file_path}", 4000)
        self._refresh_recent_menu()

    def _on_missing_firmware(self, missing_entries: list) -> None:
        names = "\n".join(f"  - {e.file_path}" for e in missing_entries[:15])
        more = "" if len(missing_entries) <= 15 else f"\n  ...and {len(missing_entries) - 15} more"
        QMessageBox.warning(
            self, "Missing Firmware Files",
            f"{len(missing_entries)} firmware file(s) referenced by this project could not be found:\n\n"
            f"{names}{more}\n\nThe project has still been loaded. Missing files are highlighted in the "
            f"Firmware panel — use 'Add BIN...' to relink them.",
        )

    def _on_load_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Could Not Open Project", message)

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        recents = get_recent_projects()
        if not recents:
            action = QAction("(no recent projects)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
            return
        for path in recents:
            action = QAction(path, self)
            action.triggered.connect(lambda _checked, p=path: self._on_open_project(p))
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Projects", self)
        clear_action.triggered.connect(self._on_clear_recent_projects)
        self.recent_menu.addAction(clear_action)

    def _on_clear_recent_projects(self) -> None:
        reply = QMessageBox.question(
            self, "Clear Recent Projects",
            "Remove all entries from the Recent Projects list?\n\n"
            "This does not delete any project files, it only clears the list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        clear_recent_projects()
        self._refresh_recent_menu()
        self.statusBar().showMessage("Recent Projects list cleared.", 3000)

    # ------------------------------------------------------------------
    # Ports / dashboard
    # ------------------------------------------------------------------
    def _on_ports_changed(self, ports: list) -> None:
        self._connected_ports = {p.device for p in ports}
        self.settings_widget.refresh_available_ports()
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        self.dashboard.refresh(self.device_controller.devices(), self._connected_ports)

    # ------------------------------------------------------------------
    # Settings / theme / updates / about
    # ------------------------------------------------------------------
    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec():
            dialog.save()
            self._apply_theme(dialog.theme_combo.currentText())

    def _apply_theme(self, theme_name: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet_for(theme_name))
        self.settings.setValue("theme", theme_name)

    def _toggle_theme(self) -> None:
        current = self.settings.value("theme", "dark")
        self._apply_theme("light" if current == "dark" else "dark")

    def _on_check_updates(self) -> None:
        self.statusBar().showMessage("Checking for updates...", 4000)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = check_for_update()
        finally:
            QApplication.restoreOverrideCursor()

        if info is None:
            QMessageBox.information(
                self, "Check for Updates",
                f"You are running {APP_NAME} v{APP_VERSION}, which is up to date.",
            )
            return

        asset_note = f"\n\nFile: {info.asset_name}" if info.asset_name else ""
        reply = QMessageBox.question(
            self, "Update Available",
            f"A newer version is available: v{info.version} (you have v{APP_VERSION}).{asset_note}\n\n"
            f"This will open the download in your browser and close {APP_NAME} so the "
            "installer can replace the running files. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        QDesktopServices.openUrl(QUrl(info.target_url))
        self.close()

    @staticmethod
    def _load_window_icon() -> QIcon:
        icon = QIcon()
        svg_path = resource_path("icons", "app_icon.svg")
        ico_path = resource_path("icons", "app_icon.ico")
        if svg_path.is_file():
            icon.addFile(str(svg_path))
        if ico_path.is_file():
            icon.addFile(str(ico_path))
        return icon

    def _on_about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            f"<p>Version {APP_VERSION}</p>"
            "<p>Publisher: Somangshu Das — "
            "<a href=\"https://github.com/SomangshuDas\">github.com/SomangshuDas</a></p>"
            "<p>A production-grade, parallel multi-device ESP32 flashing tool built on the "
            "official <b>esptool</b> backend.</p>"
            "<p>Runs on Windows, macOS, and Linux.</p>"
            "<p>Built with Python, PySide6, and pyserial.</p>",
        )

    # ------------------------------------------------------------------
    # Window layout persistence
    # ------------------------------------------------------------------
    def _restore_window_layout(self) -> None:
        geometry = self.settings.value("window_geometry")
        state = self.settings.value("window_state")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
            self._had_saved_geometry = True
        if isinstance(state, QByteArray):
            self.restoreState(state)

    def show_startup(self) -> None:
        """
        Show the main window at application startup. First-ever launch (no
        saved geometry yet) opens maximized so the app fills the screen by
        default; once the user has resized/moved it, their saved layout is
        respected on subsequent launches instead of forcing maximize again.
        """
        if self._had_saved_geometry:
            self.show()
        else:
            self.showMaximized()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.flash_controller.any_busy():
            confirm = QMessageBox.question(
                self, "Flashing In Progress",
                "One or more devices are still flashing. Exit anyway? Active uploads will be cancelled.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.flash_controller.cancel_all()

        if not self._confirm_discard_changes():
            event.ignore()
            return

        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        for console in self._live_consoles.values():
            console.close()
        event.accept()
