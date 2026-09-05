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
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from app.logging_setup.logger import configure_logging
from app.ui.widgets import make_scrollable
from app.utilities.app_settings import get_settings
from app.utilities.constants import (
    AUTOSAVE_INTERVAL_LABELS,
    AUTOSAVE_INTERVAL_OPTIONS,
    BAUD_RATES,
    DEFAULT_AUTOSAVE_INTERVAL_MINUTES,
    DEFAULT_BAUD,
    DEFAULT_ENABLED_SOUND_EVENTS,
    DEFAULT_FLASH_MODE,
    DEFAULT_MERGE_OUTPUT_LOCATION,
    DEFAULT_MERGE_POST_ACTION,
    DEFAULT_MERGED_BIN_FILENAME,
    DEFAULT_SOUNDS_ENABLED,
    DEFAULT_THEME,
    FLASH_MODES,
    FLASH_STALL_TIMEOUT_MAX_SECONDS,
    FLASH_STALL_TIMEOUT_MIN_SECONDS,
    FLASH_STALL_TIMEOUT_SECONDS,
    MERGE_POST_ACTION_LABELS,
    MERGE_POST_ACTIONS,
    SETTINGS_KEY_AUTOSAVE_INTERVAL,
    SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS,
    SETTINGS_KEY_MERGE_DEFAULT_FILENAME,
    SETTINGS_KEY_MERGE_DEFAULT_LOCATION,
    SETTINGS_KEY_MERGE_POST_ACTION,
    SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX,
    SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX,
    SETTINGS_KEY_SOUNDS_ENABLED,
    SETTINGS_KEY_THEME,
    SOUND_EVENT_LABELS,
    SOUND_EVENTS,
    THEME_OPTION_LABELS,
    THEME_OPTIONS,
)
from app.utilities.sound_player import play_preview_sound


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

        logs_button = QPushButton("Open Logs Folder")
        logs_button.clicked.connect(self._open_logs_folder)
        layout.addWidget(logs_button)
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

    def selected_theme(self) -> str:
        return self.theme_combo.currentData()

    def save(self) -> None:
        self.settings.setValue(SETTINGS_KEY_THEME, self.theme_combo.currentData())
        self.settings.setValue("default_baud", int(self.baud_combo.currentText()))
        self.settings.setValue("default_flash_mode", self.flash_mode_combo.currentText())
        self.settings.setValue(SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS, self.stall_timeout_spin.value())
        self.settings.setValue(SETTINGS_KEY_AUTOSAVE_INTERVAL, int(self.autosave_combo.currentData()))
        self.settings.setValue(SETTINGS_KEY_MERGE_DEFAULT_FILENAME, self.merge_filename_edit.text().strip() or DEFAULT_MERGED_BIN_FILENAME)
        self.settings.setValue(SETTINGS_KEY_MERGE_DEFAULT_LOCATION, self.merge_location_edit.text().strip())
        self.settings.setValue(SETTINGS_KEY_MERGE_POST_ACTION, self.merge_post_action_combo.currentData())

        self.settings.setValue(SETTINGS_KEY_SOUNDS_ENABLED, self.sounds_enabled_check.isChecked())
        for event, check in self._sound_event_checks.items():
            self.settings.setValue(f"{SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX}{event}", check.isChecked())
        for event, path_edit in self._sound_event_paths.items():
            self.settings.setValue(f"{SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX}{event}", path_edit.text().strip())
