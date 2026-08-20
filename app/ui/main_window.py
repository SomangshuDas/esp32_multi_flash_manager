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
  - Theme switching (with live System Default detection) and persistent
    window layout via AppSettings
  - Dynamic chip-support detection (queried from esptool at startup) fed
    into every chip dropdown/validator
  - Interface Lock: Settings Lock and Full Lock, grouped under Tools -> Lock Interface

This module intentionally contains no flashing logic and no file-format
logic itself — it delegates to the controllers/managers and only handles
wiring + user interaction.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QByteArray, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon, QKeySequence
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
from app.device_manager.port_scanner import list_available_ports
from app.firmware_manager.auto_detect import scan_firmware_folder
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
from app.ui.lock_overlay import LockOverlay
from app.ui.profile_dialog import ProfileDialog
from app.ui.serial_monitor import SerialMonitorWidget
from app.ui.settings_dialog import SettingsDialog
from app.ui.shortcuts_dialog import ShortcutsDialog
from app.ui.theme import stylesheet_for
from app.ui.validation_dialog import ValidationReportDialog
from app.utilities.app_settings import get_settings
from app.utilities.chip_detect import detect_supported_chips, find_unsupported_chips
from app.utilities.constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_SERIAL_MONITOR_BAUD,
    DEFAULT_THEME,
    LIVE_LOG_MAX_LINES,
    PROJECT_FILE_FILTER,
    SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH,
    SETTINGS_KEY_THEME,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    USER_MANUAL_URL,
)
from app.utilities.helpers import resource_path, safe_filename
from app.utilities.shortcuts import get_shortcuts, save_shortcuts
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

        # ---------------- Chip support (dynamic, from esptool) ----------------
        # Queried once at startup rather than hardcoded so newly-added
        # esptool chip targets show up automatically (see chip_detect.py).
        chip_result = detect_supported_chips()
        self.supported_chips: list[str] = chip_result.chips
        self._chip_detection = chip_result

        # ---------------- Controllers ----------------
        self.project_controller = ProjectController(self)
        self.device_controller = DeviceController(self.project_controller.project, self)
        self.flash_controller = FlashController(self)
        self.port_watcher = PortWatcher(self)

        self._live_consoles: dict[str, LiveConsoleWidget] = {}
        self._serial_monitors: dict[str, SerialMonitorWidget] = {}
        self._device_log_buffers: dict[str, list[str]] = {}
        self._connected_ports: set[str] = set()
        self._had_saved_geometry = False
        self._all_actions: list[QAction] = []
        self._shortcut_actions: dict[str, QAction] = {}
        self._factory_mode_locked = False
        # Menu actions that Settings Lock disables on top of
        # the widget-level locks (see _set_factory_mode_locked).
        self._factory_lock_actions: list[QAction] = []

        self._build_ui()
        self._build_menus_and_toolbar()
        self._wire_signals()
        self.firmware_panel.set_supported_chips(self.supported_chips)
        self.settings_widget.set_chip_options(self.supported_chips)
        self._apply_theme(self.settings.value(SETTINGS_KEY_THEME, DEFAULT_THEME))
        self._connect_system_theme_watcher()
        if not chip_result.dynamic:
            logger.warning(
                "Chip support list is using the built-in fallback (esptool "
                "detection failed: %s)", chip_result.error,
            )

        # Interface Lock overlay: created hidden, covers the whole window
        # (see resizeEvent) only while locked.
        self.lock_overlay = LockOverlay(self)
        self.lock_overlay.unlock_attempted.connect(self._on_unlock_attempt)
        self.lock_overlay.hide()

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
        self.main_splitter = splitter

        self.device_panel = DevicePanel()

        right_tabs = QTabWidget()
        self.settings_tabs = right_tabs
        self.firmware_panel = FirmwarePanel()
        self.settings_widget = DeviceSettingsWidget()
        right_tabs.addTab(self.firmware_panel, "Firmware")
        right_tabs.addTab(self.settings_widget, "Device Settings")

        # Device list on the left, centralised Firmware + Device Settings
        # tabs on the right.
        splitter.addWidget(self.device_panel)
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
        self._add_action(file_menu, "&New Project", "", self._on_new_project, action_id="new_project")
        self._add_action(file_menu, "&Open Project...", "", self._on_open_project, action_id="open_project")
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Project", "", self._on_save_project, action_id="save_project")
        self._add_action(file_menu, "Save Project &As...", "", self._on_save_project_as, action_id="save_project_as")
        self._add_action(file_menu, "Rena&me Project...", "", self._on_rename_project)
        file_menu.addSeparator()
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_menu()
        file_menu.addSeparator()
        self._add_action(file_menu, "E&xit", "", self.close, action_id="exit_app")

        # ---- Devices menu ----
        devices_menu = menu_bar.addMenu("&Devices")
        self._add_action(
            devices_menu, "Add Device", "", self.device_panel.add_device_requested.emit, action_id="add_device",
        )
        batch_edit_action = self._add_action(devices_menu, "Batch Edit...", "", self._on_batch_edit, action_id="batch_edit")
        profiles_action = self._add_action(devices_menu, "Firmware Profiles...", "", self._on_open_profiles)
        devices_menu.addSeparator()
        assign_firmware_action = self._add_action(
            devices_menu, "Assign Firmware Set to Devices...", "",
            self._on_assign_firmware_set, action_id="assign_firmware_set",
        )
        # These all mutate ports/firmware/flash settings across one or more
        # devices, so Settings Lock disables them alongside
        # the Firmware/Device Settings panels themselves.
        self._factory_lock_actions.extend([batch_edit_action, profiles_action, assign_firmware_action])

        # ---- Flash menu ----
        flash_menu = menu_bar.addMenu("&Flash")
        self._add_action(flash_menu, "Upload Selected", "", self._on_upload_selected, action_id="upload_selected")
        self._add_action(flash_menu, "Upload All", "", self._on_upload_all, action_id="upload_all")
        self._add_action(flash_menu, "Cancel Selected", "", self._on_cancel_selected)
        self._add_action(flash_menu, "Cancel All", "", self._on_cancel_all, action_id="cancel_all")
        self._add_action(flash_menu, "Retry Failed", "", self._on_retry_failed)
        self._add_action(flash_menu, "Retry Selected", "", self._on_retry_selected)

        # ---- View menu ----
        view_menu = menu_bar.addMenu("&View")
        self._add_action(view_menu, "Toggle Dark/Light Theme", "", self._toggle_theme, action_id="toggle_theme")
        view_menu.addAction(self.history_dock.toggleViewAction())

        # ---- Tools menu ----
        tools_menu = menu_bar.addMenu("&Tools")
        self._add_action(tools_menu, "Settings...", "", self._on_open_settings)
        self._add_action(tools_menu, "Keyboard Shortcuts...", "", self._on_open_shortcuts_dialog)
        self._add_action(tools_menu, "Check for Updates...", "", self._on_check_updates)
        tools_menu.addSeparator()
        self._add_action(
            tools_menu, "Open Serial Monitor...", "", self._on_open_serial_monitor_dialog,
            action_id="open_serial_monitor",
        )
        tools_menu.addSeparator()
        self._add_action(tools_menu, "Set Interface Lock Key...", "", self._on_set_lock_key)
        lock_menu = tools_menu.addMenu("Lock Interface")
        self.factory_lock_action = self._add_action(
            lock_menu, "Settings Lock", "", self._on_toggle_factory_lock,
            checkable=True, action_id="factory_mode_lock",
        )
        self._add_action(lock_menu, "Full Lock", "", self._on_lock_interface, action_id="lock_interface")

        # ---- Help menu ----
        help_menu = menu_bar.addMenu("&Help")
        self._add_action(help_menu, "User Manual", "", self._on_open_user_manual)
        help_menu.addSeparator()
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

    def _add_action(
        self, target, text: str, shortcut: str, slot, checkable: bool = False, action_id: str = "",
    ) -> QAction:
        """
        Create a QAction wired to `slot`. If `action_id` is given, its
        keyboard shortcut is resolved from the user's (possibly customised)
        shortcut map instead of the literal `shortcut` argument, and the
        action is tracked in `self._shortcut_actions` so the Shortcuts
        dialog can re-apply a change live without rebuilding every menu.
        Actions without an `action_id` keep a fixed, non-customisable
        shortcut (pass "" for none, e.g. toolbar-only duplicates).
        """
        action = QAction(text, self)
        resolved_shortcut = shortcut
        if action_id:
            resolved_shortcut = get_shortcuts().get(action_id, shortcut)
            self._shortcut_actions[action_id] = action
        if resolved_shortcut:
            action.setShortcut(QKeySequence(resolved_shortcut))
        if checkable:
            action.setCheckable(True)
            action.toggled.connect(slot)
        else:
            action.triggered.connect(slot)
        target.addAction(action)
        # Tracked so Interface Lock can disable every shortcut/menu action
        # in one pass (a disabled QMenuBar alone does not stop a QAction's
        # window-level keyboard shortcut from still firing).
        self._all_actions.append(action)
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
        self.device_panel.serial_monitor_requested.connect(self._on_serial_monitor_requested_for_device)
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
        # A device that's mid-flash (Preparing/Connecting/Erasing/Uploading/
        # Verifying) must not be removed out from under its own live
        # FlashWorker -- that thread still holds a reference to this exact
        # DeviceConfig and keeps emitting signals for a device_id the UI
        # would otherwise have already dropped. Removal is blocked on
        # `flash_controller.is_busy()`, which only reflects that specific
        # in-flight flash -- merely having the device's Live Output/Log
        # window or a Serial Monitor open on its port is unaffected, since
        # neither of those set an ACTIVE_STATUSES status on the device.
        busy_ids = [did for did in device_ids if self.flash_controller.is_busy(did)]
        if busy_ids:
            busy_names = [
                d.name for d in self.device_controller.devices() if d.id in busy_ids
            ]
            QMessageBox.warning(
                self, "Remove Devices",
                "Cannot remove while flashing is in progress: "
                f"{', '.join(busy_names)}. Wait for the upload to finish or cancel it first.",
            )
            device_ids = [did for did in device_ids if did not in busy_ids]
            if not device_ids:
                return

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
        locked = device is not None and self.flash_controller.is_busy(device.id)
        self.settings_widget.set_device(device, locked=locked)

    def _on_device_config_changed(self, device_id: str) -> None:
        device = self.device_controller.get_device(device_id)
        if device:
            self.device_panel.update_device_summary(device)
            if self.settings_widget.current_device_id() == device_id:
                self.settings_widget.refresh_display()
        self.project_controller.mark_dirty()

    def _on_device_updated(self, device_id: str) -> None:
        device = self.device_controller.get_device(device_id)
        if device:
            self.device_panel.update_device_summary(device)
            if self.settings_widget.current_device_id() == device_id:
                self.settings_widget.refresh_display()

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
    def _exclude_busy_devices(self, device_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Split `device_ids` into (safe_ids, busy_names). Batch Edit, Assign
        Firmware Set, and Firmware Profile application all rewrite a
        device's ports/firmware/flash settings -- doing that to a device
        that's mid-upload would either be silently overwritten once the
        upload finishes or corrupt what's currently being flashed. Saving
        the project itself is unaffected by this and stays allowed at all
        times, per the "(Saving Allowed)" carve-out for this restriction.
        """
        safe_ids: list[str] = []
        busy_names: list[str] = []
        for device_id in device_ids:
            if self.flash_controller.is_busy(device_id):
                device = self.device_controller.get_device(device_id)
                busy_names.append(device.name if device else device_id)
            else:
                safe_ids.append(device_id)
        return safe_ids, busy_names

    def _on_open_profiles(self) -> None:
        device_id = self.device_panel.selected_device_ids()
        device = self.device_controller.get_device(device_id[0]) if device_id else None
        if device is None:
            QMessageBox.information(self, "Firmware Profiles", "Select a device first.")
            return
        if self.flash_controller.is_busy(device.id):
            QMessageBox.warning(
                self, "Firmware Profiles",
                f"'{device.name}' is currently uploading. Wait for it to finish (or cancel it) "
                "before applying a firmware profile.",
            )
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
        dialog = BatchEditDialog(len(selected_ids), self, supported_chips=self.supported_chips)
        if dialog.exec():
            field = dialog.selected_field()
            value = dialog.selected_value()
            if dialog.apply_to_all():
                target_ids = [d.id for d in self.device_controller.devices()]
            else:
                if not selected_ids:
                    QMessageBox.information(self, "Batch Edit", "No devices selected.")
                    return
                target_ids = selected_ids

            target_ids, busy_names = self._exclude_busy_devices(target_ids)
            if busy_names:
                QMessageBox.warning(
                    self, "Batch Edit",
                    "Skipped currently-uploading device(s): " + ", ".join(busy_names),
                )
            if not target_ids:
                return

            self.device_controller.apply_to_selected(target_ids, field, value)
            self.device_panel.rebuild(self.device_controller.devices())
            selected = self.device_panel.selected_device_ids()
            if selected:
                self._on_device_selected(selected[0])
            self.project_controller.mark_dirty()

    # ------------------------------------------------------------------
    # Assign Firmware Set to Devices
    # ------------------------------------------------------------------
    def _on_assign_firmware_set(self) -> None:
        """
        Import one firmware folder (same auto-detect used everywhere else
        in the app) and stamp an independent copy of the resulting BIN/
        address list onto many devices at once -- one firmware set, a
        whole bench of identical target devices, applied to either all
        devices or just the current selection.
        """
        folder = QFileDialog.getExistingDirectory(self, "Select Firmware Folder")
        if not folder:
            return
        entries = scan_firmware_folder(folder)
        if not entries:
            QMessageBox.information(self, "Assign Firmware Set", "No .bin files were found in that folder.")
            return

        selected_ids = self.device_panel.selected_device_ids()
        all_ids = [d.id for d in self.device_controller.devices()]
        if not all_ids:
            QMessageBox.information(self, "Assign Firmware Set", "Add at least one device first.")
            return

        target_ids = self._choose_assign_firmware_targets(entries, folder, selected_ids, all_ids)
        if target_ids is None:
            return

        target_ids, busy_names = self._exclude_busy_devices(target_ids)
        if busy_names:
            QMessageBox.warning(
                self, "Assign Firmware Set",
                "Skipped currently-uploading device(s): " + ", ".join(busy_names),
            )
        if not target_ids:
            return

        updated = self.device_controller.apply_firmware_to_devices(target_ids, entries)
        self.device_panel.rebuild(self.device_controller.devices())
        current = self.device_panel.selected_device_ids()
        if current:
            self._on_device_selected(current[0])
        self.project_controller.mark_dirty()
        self.statusBar().showMessage(
            f"Applied firmware set ({len(entries)} file(s)) to {updated} device(s).", 4000,
        )

    def _choose_assign_firmware_targets(
        self, entries: list, folder: str, selected_ids: list[str], all_ids: list[str],
    ) -> list[str] | None:
        """Explicitly ask whether to apply to All Devices or Selected
        Devices (only offered when something is actually selected).
        Returns the chosen id list, or None if the user cancelled."""
        box = QMessageBox(self)
        box.setWindowTitle("Assign Firmware Set")
        box.setText(f"Apply the {len(entries)} firmware file(s) from\n{folder}\n\nto which devices?")
        all_button = box.addButton(f"All Devices ({len(all_ids)})", QMessageBox.ButtonRole.AcceptRole)
        selected_button = None
        if selected_ids:
            selected_button = box.addButton(
                f"Selected Devices ({len(selected_ids)})", QMessageBox.ButtonRole.AcceptRole,
            )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == all_button:
            return all_ids
        if selected_button is not None and clicked == selected_button:
            return selected_ids
        return None

    # ------------------------------------------------------------------
    # Interface lock
    # ------------------------------------------------------------------
    @staticmethod
    def _hash_lock_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _on_set_lock_key(self) -> bool:
        """Prompt for a new unlock key (entered twice) and store its hash.
        Returns True if a key was set."""
        key, ok = QInputDialog.getText(
            self, "Set Interface Lock Key", "New unlock key:", QLineEdit.EchoMode.Password,
        )
        if not ok or not key:
            return False
        confirm, ok = QInputDialog.getText(
            self, "Set Interface Lock Key", "Confirm unlock key:", QLineEdit.EchoMode.Password,
        )
        if not ok or confirm != key:
            QMessageBox.warning(self, "Set Interface Lock Key", "Keys did not match. Not changed.")
            return False
        self.settings.setValue(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH, self._hash_lock_key(key))
        QMessageBox.information(self, "Set Interface Lock Key", "Interface lock key saved.")
        return True

    # ------------------------------------------------------------------
    # Settings Lock
    # ------------------------------------------------------------------
    def _on_toggle_factory_lock(self, checked: bool) -> None:
        """
        Settings Lock: unlike Full Lock, the window stays
        usable (uploads, Serial Monitor, viewing logs still work) -- only
        the controls that change WHAT gets flashed and WHERE are disabled:
        ports, chip/flash settings, the firmware list (including Merge
        Bins), Batch Edit, Assign Firmware Set, Firmware Profiles, and
        deleting devices. See _set_factory_mode_locked for the actual
        widget-level enforcement.
        """
        if checked:
            if not self.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH):
                QMessageBox.information(
                    self, "Settings Lock",
                    "No unlock key is set yet. Set one now, then try again.",
                )
                self.factory_lock_action.blockSignals(True)
                self.factory_lock_action.setChecked(False)
                self.factory_lock_action.blockSignals(False)
                self._on_set_lock_key()
                return
            self._set_factory_mode_locked(True)
            self.statusBar().showMessage("Settings locked.", 4000)
        else:
            key, ok = QInputDialog.getText(
                self, "Unlock Settings", "Unlock key:", QLineEdit.EchoMode.Password,
            )
            stored_hash = self.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH)
            if not ok:
                # User cancelled the prompt -- stay locked, keep the
                # checkbox reflecting reality instead of silently unlocking.
                self.factory_lock_action.blockSignals(True)
                self.factory_lock_action.setChecked(True)
                self.factory_lock_action.blockSignals(False)
                return
            if not key or self._hash_lock_key(key) != stored_hash:
                QMessageBox.warning(self, "Unlock Settings", "Incorrect key.")
                self.factory_lock_action.blockSignals(True)
                self.factory_lock_action.setChecked(True)
                self.factory_lock_action.blockSignals(False)
                return
            self._set_factory_mode_locked(False)
            self.statusBar().showMessage("Settings unlocked.", 3000)

    def _set_factory_mode_locked(self, locked: bool) -> None:
        self._factory_mode_locked = locked
        self.firmware_panel.set_factory_locked(locked)
        self.settings_widget.set_factory_locked(locked)
        self.device_panel.set_deletion_locked(locked)
        for action in self._factory_lock_actions:
            action.setEnabled(not locked)

    def _on_lock_interface(self) -> None:
        if not self.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH):
            QMessageBox.information(
                self, "Full Lock",
                "No unlock key is set yet. Set one now, then Full Lock again.",
            )
            self._on_set_lock_key()
            return

        open_windows = self._open_secondary_window_titles()
        if open_windows:
            QMessageBox.information(
                self, "Full Lock",
                "Close the following window(s) before locking the interface:\n\n"
                + "\n".join(f"- {title}" for title in open_windows),
            )
            return

        self.menuBar().setEnabled(False)
        self.centralWidget().setEnabled(False)
        for dock in self.findChildren(QDockWidget):
            dock.setEnabled(False)
        for toolbar in self.findChildren(QToolBar):
            toolbar.setEnabled(False)
        for action in self._all_actions:
            action.setEnabled(False)
        self._position_lock_overlay()
        self.lock_overlay.reset_and_show()
        self.statusBar().showMessage("Interface locked.", 4000)

    def _open_secondary_window_titles(self) -> list[str]:
        """Titles of every currently-visible Logs / Serial Monitor window --
        esptool output consoles and serial monitors are independent,
        undocked windows that Interface Lock cannot reach or disable, so
        locking with one left open would leave a hole in the lock. Instead
        we ask the user to close them first."""
        titles: list[str] = []
        for console in self._live_consoles.values():
            if console.isVisible():
                titles.append(console.windowTitle())
        for monitor in self._serial_monitors.values():
            if monitor.isVisible():
                titles.append(monitor.windowTitle())
        return titles

    def _on_unlock_attempt(self, entered_key: str) -> None:
        stored_hash = self.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH)
        if not entered_key or self._hash_lock_key(entered_key) != stored_hash:
            self.lock_overlay.show_error()
            return

        self.lock_overlay.hide()
        self.menuBar().setEnabled(True)
        self.centralWidget().setEnabled(True)
        for dock in self.findChildren(QDockWidget):
            dock.setEnabled(True)
        for toolbar in self.findChildren(QToolBar):
            toolbar.setEnabled(True)
        for action in self._all_actions:
            action.setEnabled(True)
        self.statusBar().showMessage("Interface unlocked.", 3000)

    def _position_lock_overlay(self) -> None:
        self.lock_overlay.setGeometry(0, 0, self.width(), self.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if hasattr(self, "lock_overlay") and self.lock_overlay.isVisible():
            self._position_lock_overlay()

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

        report = validate_devices(
            devices, self._connected_ports, self._monitor_ports(), supported_chips=self.supported_chips,
        )
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
        # Lock/unlock the Settings panel in step with this device's own
        # busy state, not just the status string, so it lines up exactly
        # with what _busy_ports()/remove-device use -- e.g. COMPLETED still
        # briefly reports is_busy() while the worker thread unwinds.
        if self.settings_widget.current_device_id() == device_id:
            self.settings_widget.set_locked(self.flash_controller.is_busy(device_id))
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
        self._warn_about_unsupported_chips(project.devices)

    def _warn_about_unsupported_chips(self, devices) -> None:
        """
        Clearly warn (once per load) if this project uses a chip the
        currently-installed esptool no longer reports support for -- e.g.
        the project was created with a newer/older esptool, or a chip
        target esptool dropped. The project still loads and nothing is
        changed automatically; this only surfaces the problem before the
        user discovers it the hard way at Upload time.
        """
        unsupported = find_unsupported_chips(devices, self.supported_chips)
        if not unsupported:
            return
        lines = "\n".join(f"  - {name}: '{chip}'" for name, chip in unsupported.items())
        QMessageBox.warning(
            self, "Unsupported Chip(s) in This Project",
            "The installed esptool does not report support for the chip type used by "
            f"the following device(s):\n\n{lines}\n\n"
            "Uploading to these devices will likely fail until the chip type is corrected "
            "in Device Settings or esptool is updated.\n\n"
            f"Chips currently supported: {', '.join(self.supported_chips)}",
        )

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
    # Serial Monitor
    # ------------------------------------------------------------------
    def _busy_ports(self) -> set[str]:
        """Ports currently mid-upload, across every device -- used to
        refuse opening a Serial Monitor on a port esptool is using."""
        return {
            d.com_port for d in self.device_controller.devices()
            if d.com_port and self.flash_controller.is_busy(d.id)
        }

    def _monitor_ports(self) -> set[str]:
        """Ports with a *connected* Serial Monitor open -- used by the
        pre-upload validator to refuse starting a flash while the port is
        already held open elsewhere."""
        return {port for port, monitor in self._serial_monitors.items() if monitor.is_connected()}

    def _on_open_serial_monitor_dialog(self) -> None:
        ports = list_available_ports()
        if not ports:
            QMessageBox.information(self, "Serial Monitor", "No serial ports were detected.")
            return
        port_names = [p.device for p in ports]
        port, ok = QInputDialog.getItem(self, "Open Serial Monitor", "Port:", port_names, 0, False)
        if not ok or not port:
            return
        self._open_serial_monitor_for_port(port)

    def _on_serial_monitor_requested_for_device(self, device_id: str) -> None:
        device = self.device_controller.get_device(device_id)
        if device is None:
            return
        if not device.com_port:
            QMessageBox.information(self, "Serial Monitor", "This device has no port selected yet.")
            return
        self._open_serial_monitor_for_port(device.com_port, device.baud_rate)

    def _open_serial_monitor_for_port(self, port: str, baud: int | None = None) -> None:
        if port in self._busy_ports():
            QMessageBox.warning(
                self, "Serial Monitor",
                f"Port {port} is currently uploading firmware. Wait for the upload to finish "
                "before opening the Serial Monitor.",
            )
            return
        existing = self._serial_monitors.get(port)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        monitor = SerialMonitorWidget(port, baud or DEFAULT_SERIAL_MONITOR_BAUD)
        monitor.closed.connect(self._on_serial_monitor_closed)
        self._serial_monitors[port] = monitor
        monitor.show()

    def _on_serial_monitor_closed(self, port: str) -> None:
        self._serial_monitors.pop(port, None)

    # ------------------------------------------------------------------
    # Settings / theme / updates / about
    # ------------------------------------------------------------------
    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec():
            dialog.save()
            self._apply_theme(dialog.selected_theme())

    def _on_open_shortcuts_dialog(self) -> None:
        dialog = ShortcutsDialog(self)
        if dialog.exec():
            mapping = dialog.result_mapping()
            save_shortcuts(mapping)
            for action_id, action in self._shortcut_actions.items():
                action.setShortcut(QKeySequence(mapping.get(action_id, "")))
            self.statusBar().showMessage("Keyboard shortcuts updated.", 3000)

    def _on_open_user_manual(self) -> None:
        QDesktopServices.openUrl(QUrl(USER_MANUAL_URL))

    def _apply_theme(self, theme_name: str) -> None:
        """Apply `theme_name` ("system"/"dark"/"light") and persist the
        PREFERENCE as given -- "system" is stored as-is (not the resolved
        dark/light), so a later OS theme change is picked up automatically
        the next time this is called (see _connect_system_theme_watcher)."""
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet_for(theme_name))
        self.settings.setValue(SETTINGS_KEY_THEME, theme_name)

    def _toggle_theme(self) -> None:
        current = self.settings.value(SETTINGS_KEY_THEME, DEFAULT_THEME)
        self._apply_theme(THEME_LIGHT if current == THEME_DARK else THEME_DARK)

    def _connect_system_theme_watcher(self) -> None:
        """
        Re-apply the theme whenever the OS's color scheme changes AND the
        active preference is "System Default" -- so switching the desktop
        from light to dark (or back) while the app is already open is
        reflected immediately, not just on the next launch.
        Qt's colorSchemeChanged signal needs Qt 6.5+ (this project already
        requires PySide6>=6.6.0); if it's unavailable for any reason this
        degrades gracefully to "system theme is resolved at launch/Settings
        time only", never a crash.
        """
        try:
            style_hints = QGuiApplication.styleHints()
            style_hints.colorSchemeChanged.connect(self._on_system_theme_changed)
        except Exception:  # noqa: BLE001 - live theme detection is a nice-to-have, not critical
            logger.exception("Could not connect to the OS color-scheme-changed signal")

    def _on_system_theme_changed(self, *_args) -> None:
        if self.settings.value(SETTINGS_KEY_THEME, DEFAULT_THEME) == THEME_SYSTEM:
            self._apply_theme(THEME_SYSTEM)
            self.statusBar().showMessage("System theme changed — appearance updated.", 3000)

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
        if self.lock_overlay.isVisible():
            # Refuse to close while locked -- otherwise Alt+F4 / the
            # window-manager close button would bypass the lock entirely.
            # Unlock first (Tools -> Lock Interface -> Full Lock), then Exit.
            event.ignore()
            self.statusBar().showMessage("Unlock the interface before closing.", 4000)
            return

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
        for monitor in list(self._serial_monitors.values()):
            monitor.close()
        event.accept()
