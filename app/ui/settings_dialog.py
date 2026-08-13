"""
settings_dialog.py
===================
Application-wide preferences: theme (dark/light), default baud rate,
default flash mode, and a shortcut to open the logs folder. Persisted
via AppSettings (settings.json under the roaming app-data folder) so
they survive across launches without touching the Windows registry.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QPushButton, QVBoxLayout, QWidget,
)

from app.logging_setup.logger import configure_logging
from app.ui.widgets import make_scrollable
from app.utilities.app_settings import get_settings
from app.utilities.constants import BAUD_RATES, DEFAULT_BAUD, DEFAULT_FLASH_MODE, FLASH_MODES


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(380, 220)
        self.settings = get_settings()

        outer_layout = QVBoxLayout(self)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self.settings.value("theme", "dark"))
        form.addRow("Theme:", self.theme_combo)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText(str(self.settings.value("default_baud", DEFAULT_BAUD)))
        form.addRow("Default Baud Rate:", self.baud_combo)

        self.flash_mode_combo = QComboBox()
        self.flash_mode_combo.addItems(FLASH_MODES)
        self.flash_mode_combo.setCurrentText(self.settings.value("default_flash_mode", DEFAULT_FLASH_MODE))
        form.addRow("Default Flash Mode:", self.flash_mode_combo)

        layout.addLayout(form)

        logs_button = QPushButton("Open Logs Folder")
        logs_button.clicked.connect(self._open_logs_folder)
        layout.addWidget(logs_button)

        outer_layout.addWidget(make_scrollable(content), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

    def _open_logs_folder(self) -> None:
        log_dir = configure_logging()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))

    def save(self) -> None:
        self.settings.setValue("theme", self.theme_combo.currentText())
        self.settings.setValue("default_baud", int(self.baud_combo.currentText()))
        self.settings.setValue("default_flash_mode", self.flash_mode_combo.currentText())
