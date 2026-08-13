"""
profile_dialog.py
==================
Lets the user pick a saved Firmware Profile (e.g. "ESP32 RFID Reader") to
apply to the currently selected device, save the current device's
configuration as a new named profile, or delete an existing one.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.firmware_manager.profiles import FirmwareProfile, delete_profile, list_profiles, save_profile
from app.models.device_model import DeviceConfig
from app.ui.widgets import make_scrollable


class ProfileDialog(QDialog):
    def __init__(self, device: DeviceConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Firmware Profiles")
        self.resize(420, 360)
        self.device = device
        self.chosen_profile: FirmwareProfile | None = None

        outer_layout = QVBoxLayout(self)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setMinimumHeight(120)
        self._reload_list()
        layout.addWidget(self.list_widget, 1)

        button_row = QHBoxLayout()
        self.save_as_button = QPushButton(f"Save '{device.name}' As New Profile...")
        self.save_as_button.clicked.connect(self._save_as_profile)
        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self._delete_selected)
        button_row.addWidget(self.save_as_button)
        button_row.addWidget(self.delete_button)
        layout.addLayout(button_row)

        outer_layout.addWidget(make_scrollable(content), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply to Device")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

    def _reload_list(self) -> None:
        self.list_widget.clear()
        for profile in list_profiles():
            item = QListWidgetItem(f"{profile.name}  ({len(profile.firmware)} file(s), {profile.chip_type})")
            item.setData(1000, profile)
            self.list_widget.addItem(item)

    def _save_as_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name.strip():
            return
        profile = FirmwareProfile.from_device(name.strip(), self.device)
        save_profile(profile)
        self._reload_list()

    def _delete_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        profile: FirmwareProfile = item.data(1000)
        confirm = QMessageBox.question(self, "Delete Profile", f"Delete profile '{profile.name}'?")
        if confirm == QMessageBox.StandardButton.Yes:
            delete_profile(profile.name)
            self._reload_list()

    def _on_accept(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Firmware Profiles", "Select a profile first, or click Cancel.")
            return
        self.chosen_profile = item.data(1000)
        self.accept()
