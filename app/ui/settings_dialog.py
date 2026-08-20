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
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from app.logging_setup.logger import configure_logging
from app.ui.widgets import make_scrollable
from app.utilities.app_settings import get_settings
from app.utilities.constants import (
    BAUD_RATES,
    DEFAULT_BAUD,
    DEFAULT_FLASH_MODE,
    DEFAULT_MERGE_OUTPUT_LOCATION,
    DEFAULT_MERGE_POST_ACTION,
    DEFAULT_MERGED_BIN_FILENAME,
    DEFAULT_THEME,
    FLASH_MODES,
    MERGE_POST_ACTION_LABELS,
    MERGE_POST_ACTIONS,
    SETTINGS_KEY_MERGE_DEFAULT_FILENAME,
    SETTINGS_KEY_MERGE_DEFAULT_LOCATION,
    SETTINGS_KEY_MERGE_POST_ACTION,
    SETTINGS_KEY_THEME,
    THEME_OPTION_LABELS,
    THEME_OPTIONS,
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(440, 340)
        self.settings = get_settings()

        outer_layout = QVBoxLayout(self)

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

        outer_layout.addWidget(make_scrollable(content), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

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
        self.settings.setValue(SETTINGS_KEY_MERGE_DEFAULT_FILENAME, self.merge_filename_edit.text().strip() or DEFAULT_MERGED_BIN_FILENAME)
        self.settings.setValue(SETTINGS_KEY_MERGE_DEFAULT_LOCATION, self.merge_location_edit.text().strip())
        self.settings.setValue(SETTINGS_KEY_MERGE_POST_ACTION, self.merge_post_action_combo.currentData())
