"""
settings_dialog.py
===================
Application-wide preferences: theme (System Default/dark/light), default
baud rate, default flash mode, Bin Merge defaults (output filename/
location, post-merge action), and a shortcut to open the logs folder.
Persisted via AppSettings (settings.json under the roaming app-data
folder) so they survive across launches without touching the Windows
registry.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from app.firmware_manager.profiles import list_profiles
from app.logging_setup.logger import configure_logging
from app.ui.widgets import make_scrollable
from app.utilities.app_settings import get_settings
from app.utilities.constants import (
    AUTOSAVE_INTERVAL_LABELS,
    AUTOSAVE_INTERVAL_OPTIONS,
    BAUD_RATES,
    DEFAULT_AUTOSAVE_INTERVAL_MINUTES,
    DEFAULT_BAUD,
    DEFAULT_DEVICE_PROFILE_NONE,
    DEFAULT_ENABLED_SOUND_EVENTS,
    DEFAULT_ENABLED_TELEMETRY,
    DEFAULT_FLASH_MODE,
    DEFAULT_JSON_LOGGING_ENABLED,
    DEFAULT_MERGE_OUTPUT_LOCATION,
    DEFAULT_MERGE_POST_ACTION,
    DEFAULT_MERGED_BIN_FILENAME,
    DEFAULT_SOUNDS_ENABLED,
    DEFAULT_THEME,
    FLASH_MODES,
    FLASH_STALL_TIMEOUT_MAX_SECONDS,
    FLASH_STALL_TIMEOUT_MIN_SECONDS,
    FLASH_STALL_TIMEOUT_SECONDS,
    LIVE_LOG_MAX_LINES,
    LIVE_LOG_MAX_LINES_MAX,
    LIVE_LOG_MAX_LINES_MIN,
    MAX_PARALLEL_FLASHES,
    MAX_PARALLEL_FLASHES_MAX,
    MAX_PARALLEL_FLASHES_MIN,
    MAX_PARALLEL_PROVISIONS,
    MAX_PARALLEL_PROVISIONS_MAX,
    MAX_PARALLEL_PROVISIONS_MIN,
    MERGE_POST_ACTION_LABELS,
    MERGE_POST_ACTIONS,
    PORT_SCAN_INTERVAL_MS,
    PORT_SCAN_INTERVAL_MS_MAX,
    PORT_SCAN_INTERVAL_MS_MIN,
    PROJECT_LOCK_STALE_SECONDS,
    PROJECT_LOCK_STALE_SECONDS_MAX,
    PROJECT_LOCK_STALE_SECONDS_MIN,
    PROVISION_STALL_TIMEOUT_MAX_SECONDS,
    PROVISION_STALL_TIMEOUT_MIN_SECONDS,
    PROVISION_STALL_TIMEOUT_SECONDS,
    SETTINGS_KEY_AUTOSAVE_INTERVAL,
    SETTINGS_KEY_DEFAULT_DEVICE_PROFILE,
    SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS,
    SETTINGS_KEY_JSON_LOGGING_ENABLED,
    SETTINGS_KEY_LIVE_LOG_MAX_LINES,
    SETTINGS_KEY_MAX_PARALLEL_FLASHES,
    SETTINGS_KEY_MAX_PARALLEL_PROVISIONS,
    SETTINGS_KEY_MERGE_DEFAULT_FILENAME,
    SETTINGS_KEY_MERGE_DEFAULT_LOCATION,
    SETTINGS_KEY_MERGE_POST_ACTION,
    SETTINGS_KEY_PORT_SCAN_INTERVAL_MS,
    SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS,
    SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS,
    SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX,
    SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX,
    SETTINGS_KEY_SOUNDS_ENABLED,
    SETTINGS_KEY_TELEMETRY_ENABLED,
    SETTINGS_KEY_THEME,
    SETTINGS_KEY_UNDO_STACK_DEPTH,
    SOUND_EVENT_LABELS,
    SOUND_EVENTS,
    THEME_OPTION_LABELS,
    THEME_OPTIONS,
    UNDO_STACK_DEPTH,
    UNDO_STACK_DEPTH_MAX,
    UNDO_STACK_DEPTH_MIN,
)
from app.utilities.diagnostics import export_diagnostics_bundle
from app.utilities.sound_player import play_preview_sound
from app.utilities.telemetry import clear_local_telemetry


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(480, 460)
        self.settings = get_settings()

        outer_layout = QVBoxLayout(self)

        tabs = QTabWidget()
        outer_layout.addWidget(tabs, 1)

        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_sounds_tab(), "Sounds")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        tabs.addTab(self._build_diagnostics_tab(), "Diagnostics")
        tabs.addTab(self._build_privacy_tab(), "Privacy")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _build_general_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self.theme_combo = QComboBox()
        for value in THEME_OPTIONS:
            self.theme_combo.addItem(THEME_OPTION_LABELS[value], value)
        current_theme = self.settings.value(SETTINGS_KEY_THEME, DEFAULT_THEME)
        index = self.theme_combo.findData(current_theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        form.addRow("Theme:", self.theme_combo)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText(str(self.settings.value("default_baud", DEFAULT_BAUD)))
        form.addRow("Default Baud Rate:", self.baud_combo)

        self.flash_mode_combo = QComboBox()
        self.flash_mode_combo.addItems(FLASH_MODES)
        self.flash_mode_combo.setCurrentText(self.settings.value("default_flash_mode", DEFAULT_FLASH_MODE))
        form.addRow("Default Flash Mode:", self.flash_mode_combo)

        self.stall_timeout_spin = QDoubleSpinBox()
        self.stall_timeout_spin.setDecimals(0)
        self.stall_timeout_spin.setRange(FLASH_STALL_TIMEOUT_MIN_SECONDS, FLASH_STALL_TIMEOUT_MAX_SECONDS)
        self.stall_timeout_spin.setSuffix(" s")
        self.stall_timeout_spin.setToolTip(
            "How long a flash or read operation can go with no output from esptool before "
            "it's treated as an unresponsive/disconnected device and aborted."
        )
        self.stall_timeout_spin.setValue(
            float(self.settings.value(SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS, FLASH_STALL_TIMEOUT_SECONDS))
        )
        form.addRow("Flash Stall Timeout:", self.stall_timeout_spin)

        self.max_parallel_spin = QSpinBox()
        self.max_parallel_spin.setRange(MAX_PARALLEL_FLASHES_MIN, MAX_PARALLEL_FLASHES_MAX)
        self.max_parallel_spin.setToolTip(
            "How many devices can flash at the same time. Devices beyond this cap wait in a "
            "queue and start automatically as running devices finish, instead of all launching "
            "at once (which can exhaust USB bandwidth or OS threads on a large bench)."
        )
        self.max_parallel_spin.setValue(
            int(self.settings.value(SETTINGS_KEY_MAX_PARALLEL_FLASHES, MAX_PARALLEL_FLASHES))
        )
        form.addRow("Max Parallel Flashes:", self.max_parallel_spin)

        # ---- Default Device Profile ----
        self.default_profile_combo = QComboBox()
        self.default_profile_combo.addItem("(none)", DEFAULT_DEVICE_PROFILE_NONE)
        for profile in list_profiles():
            self.default_profile_combo.addItem(profile.name, profile.name)
        current_default_profile = self.settings.value(SETTINGS_KEY_DEFAULT_DEVICE_PROFILE, DEFAULT_DEVICE_PROFILE_NONE)
        default_profile_index = self.default_profile_combo.findData(current_default_profile)
        self.default_profile_combo.setCurrentIndex(default_profile_index if default_profile_index >= 0 else 0)
        self.default_profile_combo.setToolTip(
            "Automatically apply this Firmware Profile's settings and firmware list to every "
            "newly-added device, instead of the app's built-in defaults."
        )
        form.addRow("Default Device Profile:", self.default_profile_combo)
        self.default_profile_combo.setAccessibleName("Default Device Profile")

        # ---- Auto-Save ----
        self.autosave_combo = QComboBox()
        for minutes in AUTOSAVE_INTERVAL_OPTIONS:
            self.autosave_combo.addItem(AUTOSAVE_INTERVAL_LABELS[minutes], minutes)
        current_autosave = int(self.settings.value(SETTINGS_KEY_AUTOSAVE_INTERVAL, DEFAULT_AUTOSAVE_INTERVAL_MINUTES))
        autosave_index = self.autosave_combo.findData(current_autosave)
        self.autosave_combo.setCurrentIndex(autosave_index if autosave_index >= 0 else 0)
        form.addRow("Auto-Save:", self.autosave_combo)
        autosave_note = QLabel(
            "New projects that have not been saved to disk yet are protected in a separate "
            "crash-recovery slot, offered back to you next time the app starts."
        )
        autosave_note.setWordWrap(True)
        autosave_note.setStyleSheet("color: #8a8f98; font-size: 11px;")
        form.addRow("", autosave_note)

        # ---- Bin Merge defaults ----
        self.merge_filename_edit = QLineEdit()
        self.merge_filename_edit.setText(
            self.settings.value(SETTINGS_KEY_MERGE_DEFAULT_FILENAME, DEFAULT_MERGED_BIN_FILENAME)
        )
        form.addRow("Default Merged Filename:", self.merge_filename_edit)

        location_row = QHBoxLayout()
        self.merge_location_edit = QLineEdit()
        self.merge_location_edit.setPlaceholderText("(same folder as firmware.bin)")
        self.merge_location_edit.setText(
            self.settings.value(SETTINGS_KEY_MERGE_DEFAULT_LOCATION, DEFAULT_MERGE_OUTPUT_LOCATION)
        )
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_merge_location)
        location_row.addWidget(self.merge_location_edit, 1)
        location_row.addWidget(browse_button)
        form.addRow("Default Merged Output Location:", location_row)

        self.merge_post_action_combo = QComboBox()
        for value in MERGE_POST_ACTIONS:
            self.merge_post_action_combo.addItem(MERGE_POST_ACTION_LABELS[value], value)
        current_action = self.settings.value(SETTINGS_KEY_MERGE_POST_ACTION, DEFAULT_MERGE_POST_ACTION)
        action_index = self.merge_post_action_combo.findData(current_action)
        self.merge_post_action_combo.setCurrentIndex(action_index if action_index >= 0 else 0)
        form.addRow("Default Post-Merge Action:", self.merge_post_action_combo)

        layout.addLayout(form)

        # ---- Provisioning (eFuse burning) ----
        provisioning_box = QGroupBox("Provisioning")
        provisioning_form = QFormLayout(provisioning_box)

        self.max_parallel_provisions_spin = QSpinBox()
        self.max_parallel_provisions_spin.setRange(MAX_PARALLEL_PROVISIONS_MIN, MAX_PARALLEL_PROVISIONS_MAX)
        self.max_parallel_provisions_spin.setToolTip(
            "How many devices can have eFuses burned at the same time during batch provisioning "
            "(Tools -> Provision Devices (Batch)...). Devices beyond this cap wait in a queue and "
            "start automatically as running devices finish."
        )
        self.max_parallel_provisions_spin.setValue(
            int(self.settings.value(SETTINGS_KEY_MAX_PARALLEL_PROVISIONS, MAX_PARALLEL_PROVISIONS))
        )
        provisioning_form.addRow("Max Parallel Provisions:", self.max_parallel_provisions_spin)

        self.provision_stall_timeout_spin = QDoubleSpinBox()
        self.provision_stall_timeout_spin.setDecimals(0)
        self.provision_stall_timeout_spin.setRange(
            PROVISION_STALL_TIMEOUT_MIN_SECONDS, PROVISION_STALL_TIMEOUT_MAX_SECONDS
        )
        self.provision_stall_timeout_spin.setSuffix(" s")
        self.provision_stall_timeout_spin.setToolTip(
            "How long an eFuse-burning (espefuse) operation can go with no output before it's "
            "treated as an unresponsive/disconnected device and aborted."
        )
        self.provision_stall_timeout_spin.setValue(
            float(self.settings.value(SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS, PROVISION_STALL_TIMEOUT_SECONDS))
        )
        provisioning_form.addRow("Provision Stall Timeout:", self.provision_stall_timeout_spin)

        layout.addWidget(provisioning_box)

        layout.addStretch(1)

        return make_scrollable(content)

    def _build_advanced_tab(self) -> QWidget:
        """Previously-hardcoded internals exposed for benches with unusual
        hardware/timing needs. Defaults match the app's previous
        hardcoded behavior, so leaving this tab untouched changes nothing."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self.port_scan_interval_spin = QSpinBox()
        self.port_scan_interval_spin.setRange(PORT_SCAN_INTERVAL_MS_MIN, PORT_SCAN_INTERVAL_MS_MAX)
        self.port_scan_interval_spin.setSuffix(" ms")
        self.port_scan_interval_spin.setSingleStep(250)
        self.port_scan_interval_spin.setToolTip(
            "How often the app polls the OS for available serial ports. Lower values notice a "
            "plugged/unplugged device sooner at the cost of slightly more CPU/USB polling."
        )
        self.port_scan_interval_spin.setValue(
            int(self.settings.value(SETTINGS_KEY_PORT_SCAN_INTERVAL_MS, PORT_SCAN_INTERVAL_MS))
        )
        form.addRow("Port Scan Interval:", self.port_scan_interval_spin)
        self.port_scan_interval_spin.setAccessibleName("Port Scan Interval")

        self.live_log_max_lines_spin = QSpinBox()
        self.live_log_max_lines_spin.setRange(LIVE_LOG_MAX_LINES_MIN, LIVE_LOG_MAX_LINES_MAX)
        self.live_log_max_lines_spin.setSingleStep(500)
        self.live_log_max_lines_spin.setToolTip(
            "How many lines of live serial/console output are kept on screen per device before "
            "older lines are dropped. Lower values use less memory on a bench with many devices."
        )
        self.live_log_max_lines_spin.setValue(
            int(self.settings.value(SETTINGS_KEY_LIVE_LOG_MAX_LINES, LIVE_LOG_MAX_LINES))
        )
        form.addRow("Live Log Max Lines:", self.live_log_max_lines_spin)
        self.live_log_max_lines_spin.setAccessibleName("Live Log Max Lines")

        self.lock_stale_spin = QSpinBox()
        self.lock_stale_spin.setRange(PROJECT_LOCK_STALE_SECONDS_MIN, PROJECT_LOCK_STALE_SECONDS_MAX)
        self.lock_stale_spin.setSuffix(" s")
        self.lock_stale_spin.setSingleStep(60)
        self.lock_stale_spin.setToolTip(
            "How old a project's .lock sidecar file must be (with no matching running process on "
            "the same machine) before it's treated as abandoned and the project can be reopened."
        )
        self.lock_stale_spin.setValue(
            int(self.settings.value(SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS, PROJECT_LOCK_STALE_SECONDS))
        )
        form.addRow("Project Lock Stale After:", self.lock_stale_spin)
        self.lock_stale_spin.setAccessibleName("Project Lock Stale After")

        self.undo_depth_spin = QSpinBox()
        self.undo_depth_spin.setRange(UNDO_STACK_DEPTH_MIN, UNDO_STACK_DEPTH_MAX)
        self.undo_depth_spin.setToolTip(
            "How many Batch Edit / Assign Firmware Set / bulk remove / CSV-or-bundle import "
            "operations Ctrl+Z can step back through. Each step keeps a full copy of the "
            "device list, so a very high value trades memory for a longer undo history."
        )
        self.undo_depth_spin.setValue(
            int(self.settings.value(SETTINGS_KEY_UNDO_STACK_DEPTH, UNDO_STACK_DEPTH))
        )
        form.addRow("Undo History Depth:", self.undo_depth_spin)
        self.undo_depth_spin.setAccessibleName("Undo History Depth")

        layout.addLayout(form)
        layout.addStretch(1)
        return make_scrollable(content)

    def _build_diagnostics_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        self.json_logging_check = QCheckBox("Enable structured JSON logging (events.jsonl)")
        self.json_logging_check.setAccessibleName("Enable structured JSON logging")
        self.json_logging_check.setToolTip(
            "In addition to the four regular text log files, also write every log record as one "
            "JSON object per line to events.jsonl -- useful if you pipe logs into a log-aggregation "
            "tool. The text logs are always written regardless of this setting."
        )
        self.json_logging_check.setChecked(
            bool(self.settings.value(SETTINGS_KEY_JSON_LOGGING_ENABLED, DEFAULT_JSON_LOGGING_ENABLED, type=bool))
        )
        layout.addWidget(self.json_logging_check)

        logs_button = QPushButton("Open Logs Folder")
        logs_button.clicked.connect(self._open_logs_folder)
        layout.addWidget(logs_button)

        bundle_button = QPushButton("Export Diagnostics Bundle...")
        bundle_button.setAccessibleName("Export Diagnostics Bundle")
        bundle_button.setToolTip(
            "Save a single .zip containing all current log files plus app/OS/Python/esptool "
            "version information -- convenient to attach to a bug report."
        )
        bundle_button.clicked.connect(self._export_diagnostics_bundle)
        layout.addWidget(bundle_button)

        layout.addStretch(1)
        return make_scrollable(content)

    def _build_privacy_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        self.telemetry_check = QCheckBox("Share anonymous usage & crash data")
        self.telemetry_check.setAccessibleName("Share anonymous usage and crash data")
        self.telemetry_check.setChecked(
            bool(self.settings.value(SETTINGS_KEY_TELEMETRY_ENABLED, DEFAULT_ENABLED_TELEMETRY, type=bool))
        )
        layout.addWidget(self.telemetry_check)

        note = QLabel(
            "Off by default. When enabled, a small number of coarse events (e.g. \"a flash batch "
            "finished\", with a device count and success/failure counts) are recorded locally to "
            "help understand how the app is used. Recorded events never include device serial "
            "numbers, COM port names, firmware file names/paths, or project names. This build does "
            "not transmit anything over the network -- events are stored locally only. See "
            "docs/PRIVACY.md for full details."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a8f98; font-size: 11px;")
        layout.addWidget(note)

        clear_button = QPushButton("Clear Local Telemetry Data")
        clear_button.setAccessibleName("Clear Local Telemetry Data")
        clear_button.clicked.connect(self._clear_local_telemetry)
        layout.addWidget(clear_button)

        layout.addStretch(1)
        return make_scrollable(content)

    def _build_sounds_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sounds_enabled_check = QCheckBox("Enable sounds")
        self.sounds_enabled_check.setChecked(
            bool(self.settings.value(SETTINGS_KEY_SOUNDS_ENABLED, DEFAULT_SOUNDS_ENABLED, type=bool))
        )
        layout.addWidget(self.sounds_enabled_check)

        events_box = QGroupBox("Events")
        events_layout = QVBoxLayout(events_box)
        self._sound_event_checks: dict[str, QCheckBox] = {}
        self._sound_event_paths: dict[str, QLineEdit] = {}
        for event in SOUND_EVENTS:
            row = QHBoxLayout()
            check = QCheckBox(SOUND_EVENT_LABELS[event])
            default_enabled = event in DEFAULT_ENABLED_SOUND_EVENTS
            check.setChecked(
                bool(self.settings.value(
                    f"{SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX}{event}", default_enabled, type=bool,
                ))
            )
            path_edit = QLineEdit()
            path_edit.setPlaceholderText("(default system beep)")
            path_edit.setText(str(self.settings.value(f"{SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX}{event}", "")))
            browse = QPushButton("Browse...")
            browse.clicked.connect(lambda _c, e=path_edit: self._browse_sound_file(e))
            test = QPushButton("Test")
            test.clicked.connect(lambda _c, e=path_edit: play_preview_sound(e.text().strip()))
            row.addWidget(check, 1)
            row.addWidget(path_edit, 2)
            row.addWidget(browse)
            row.addWidget(test)
            events_layout.addLayout(row)
            self._sound_event_checks[event] = check
            self._sound_event_paths[event] = path_edit
        layout.addWidget(events_box)
        layout.addStretch(1)

        self.sounds_enabled_check.toggled.connect(events_box.setEnabled)
        events_box.setEnabled(self.sounds_enabled_check.isChecked())

        return make_scrollable(content)

    def _browse_sound_file(self, target_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Sound File", target_edit.text(), "Sound Files (*.wav *.mp3 *.ogg)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            target_edit.setText(path)

    def _browse_merge_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Default Merged Output Location", self.merge_location_edit.text(),
            QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.merge_location_edit.setText(folder)

    def _open_logs_folder(self) -> None:
        log_dir = configure_logging()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))

    def _export_diagnostics_bundle(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Diagnostics Bundle", "diagnostics_bundle.zip", "Zip Files (*.zip)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            export_diagnostics_bundle(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not write diagnostics bundle:\n{exc}")
            return
        QMessageBox.information(self, "Diagnostics Bundle Exported", f"Saved to:\n{path}")

    def _clear_local_telemetry(self) -> None:
        clear_local_telemetry()
        QMessageBox.information(self, "Telemetry Data Cleared", "Local telemetry data has been deleted.")

    def selected_theme(self) -> str:
        return self.theme_combo.currentData()

    def save(self) -> None:
        self.settings.setValue(SETTINGS_KEY_THEME, self.theme_combo.currentData())
        self.settings.setValue("default_baud", int(self.baud_combo.currentText()))
        self.settings.setValue("default_flash_mode", self.flash_mode_combo.currentText())
        self.settings.setValue(SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS, self.stall_timeout_spin.value())
        self.settings.setValue(SETTINGS_KEY_MAX_PARALLEL_FLASHES, self.max_parallel_spin.value())
        self.settings.setValue(SETTINGS_KEY_DEFAULT_DEVICE_PROFILE, self.default_profile_combo.currentData())
        self.settings.setValue(SETTINGS_KEY_AUTOSAVE_INTERVAL, int(self.autosave_combo.currentData()))
        self.settings.setValue(SETTINGS_KEY_MERGE_DEFAULT_FILENAME, self.merge_filename_edit.text().strip() or DEFAULT_MERGED_BIN_FILENAME)
        self.settings.setValue(SETTINGS_KEY_MERGE_DEFAULT_LOCATION, self.merge_location_edit.text().strip())
        self.settings.setValue(SETTINGS_KEY_MERGE_POST_ACTION, self.merge_post_action_combo.currentData())

        self.settings.setValue(SETTINGS_KEY_MAX_PARALLEL_PROVISIONS, self.max_parallel_provisions_spin.value())
        self.settings.setValue(
            SETTINGS_KEY_PROVISION_STALL_TIMEOUT_SECONDS, self.provision_stall_timeout_spin.value()
        )

        self.settings.setValue(SETTINGS_KEY_SOUNDS_ENABLED, self.sounds_enabled_check.isChecked())
        for event, check in self._sound_event_checks.items():
            self.settings.setValue(f"{SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX}{event}", check.isChecked())
        for event, path_edit in self._sound_event_paths.items():
            self.settings.setValue(f"{SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX}{event}", path_edit.text().strip())

        self.settings.setValue(SETTINGS_KEY_PORT_SCAN_INTERVAL_MS, self.port_scan_interval_spin.value())
        self.settings.setValue(SETTINGS_KEY_LIVE_LOG_MAX_LINES, self.live_log_max_lines_spin.value())
        self.settings.setValue(SETTINGS_KEY_PROJECT_LOCK_STALE_SECONDS, self.lock_stale_spin.value())
        self.settings.setValue(SETTINGS_KEY_UNDO_STACK_DEPTH, self.undo_depth_spin.value())

        self.settings.setValue(SETTINGS_KEY_JSON_LOGGING_ENABLED, self.json_logging_check.isChecked())
        self.settings.setValue(SETTINGS_KEY_TELEMETRY_ENABLED, self.telemetry_check.isChecked())
