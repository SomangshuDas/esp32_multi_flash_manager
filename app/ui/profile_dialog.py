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
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QInputDialog, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.firmware_manager.profiles import (
    FirmwareProfile,
    delete_profile,
    export_profile_to_file,
    import_profile_from_file,
    list_profiles,
    save_profile,
)
from app.models.device_model import DeviceConfig
from app.ui.widgets import make_scrollable
from app.utilities.constants import FIRMWARE_PROFILE_FILE_FILTER
from app.utilities.helpers import safe_filename


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

        # ---- Export/Import: wraps the existing shareable-JSON-file
        # capability (FirmwareProfile is already just JSON on disk) in an
        # explicit UI flow, instead of relying on operators knowing to
        # manually locate and copy the file out of the app-data profiles
        # folder themselves.
        share_row = QHBoxLayout()
        self.export_button = QPushButton("Export Selected...")
        self.export_button.setToolTip("Save the selected profile to a file you can share (e.g. a USB drive).")
        self.export_button.clicked.connect(self._export_selected)
        self.import_button = QPushButton("Import...")
        self.import_button.setToolTip("Load a profile file exported from this app (on this or another machine).")
        self.import_button.clicked.connect(self._import_profile)
        share_row.addWidget(self.export_button)
        share_row.addWidget(self.import_button)
        layout.addLayout(share_row)

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

    def _export_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Export Profile", "Select a profile first.")
            return
        profile: FirmwareProfile = item.data(1000)
        default_name = f"{safe_filename(profile.name)}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Firmware Profile", default_name, FIRMWARE_PROFILE_FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            export_profile_to_file(profile, path)
        except OSError as exc:
            QMessageBox.critical(self, "Export Profile", f"Could not export profile:\n{exc}")
            return
        QMessageBox.information(self, "Export Profile", f"Profile '{profile.name}' exported to:\n{path}")

    def _import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Firmware Profile", "", FIRMWARE_PROFILE_FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            profile = import_profile_from_file(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Profile", f"Could not import profile:\n{exc}")
            return
        except Exception as exc:  # noqa: BLE001 - malformed JSON, etc.
            QMessageBox.critical(self, "Import Profile", f"'{path}' is not a valid firmware profile:\n{exc}")
            return

        existing_names = {p.name for p in list_profiles()}
        if profile.name in existing_names:
            confirm = QMessageBox.question(
                self, "Import Profile",
                f"A profile named '{profile.name}' already exists. Overwrite it with the imported one?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        save_profile(profile)
        self._reload_list()
        QMessageBox.information(self, "Import Profile", f"Profile '{profile.name}' imported.")

    def _on_accept(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Firmware Profiles", "Select a profile first, or click Cancel.")
            return
        self.chosen_profile = item.data(1000)
        self.accept()
