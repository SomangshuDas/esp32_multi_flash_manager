"""
firmware_panel.py
==================
Editor for the firmware (.bin) list of whichever device is currently
selected in the DevicePanel. Supports add/remove/duplicate/reorder,
drag-and-drop of files/folders from Explorer, and folder-based
auto-detection via firmware_manager.auto_detect.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.firmware_manager.auto_detect import scan_firmware_folder
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import FIRMWARE_FILE_FILTER
from app.utilities.helpers import is_valid_hex_address, normalize_hex_address

COL_ENABLED = 0
COL_FILE = 1
COL_ADDRESS = 2
COL_SIZE = 3
COL_MD5 = 4
COL_STATUS = 5


class FirmwarePanel(QWidget):
    """
    Signals
    -------
    firmware_changed(device_id) - emitted whenever the firmware list of the
                                   active device is modified in any way.
    """

    firmware_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._device: DeviceConfig | None = None

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.title_label = QLabel("Firmware — (no device selected)")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        layout.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["On", "File", "Address", "Size", "MD5", "Status"]
        )
        self.table.horizontalHeader().setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_MD5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_MD5, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add BIN...")
        self.remove_button = QPushButton("Remove")
        self.duplicate_button = QPushButton("Duplicate")
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        self.import_folder_button = QPushButton("Auto-Detect Folder...")

        self.add_button.clicked.connect(self._add_bin)
        self.remove_button.clicked.connect(self._remove_selected)
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        self.import_folder_button.clicked.connect(self._import_folder)

        for button in (
            self.add_button, self.remove_button, self.duplicate_button,
            self.move_up_button, self.move_down_button, self.import_folder_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        hint = QLabel("Tip: drag & drop .bin files or a firmware folder here to add them automatically.")
        hint.setStyleSheet("color: #9a9ca3; font-size: 11px;")
        layout.addWidget(hint)

        self._set_controls_enabled(False)

    # ------------------------------------------------------------------
    def set_device(self, device: DeviceConfig | None) -> None:
        self._device = device
        self.title_label.setText(
            f"Firmware — {device.name}" if device else "Firmware — (no device selected)"
        )
        self._set_controls_enabled(device is not None)
        self._reload_table()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.add_button, self.remove_button, self.duplicate_button,
            self.move_up_button, self.move_down_button, self.import_folder_button, self.table,
        ):
            widget.setEnabled(enabled)

    # ------------------------------------------------------------------
    def _reload_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if self._device:
            for entry in self._device.firmware:
                self._append_row(entry)
        self.table.blockSignals(False)

    def _append_row(self, entry: FirmwareEntry) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        checkbox_item.setCheckState(Qt.CheckState.Checked if entry.enabled else Qt.CheckState.Unchecked)
        checkbox_item.setData(Qt.ItemDataRole.UserRole, entry.id)
        self.table.setItem(row, COL_ENABLED, checkbox_item)

        file_item = QTableWidgetItem(entry.file_name)
        file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        file_item.setToolTip(entry.file_path)
        self.table.setItem(row, COL_FILE, file_item)

        address_item = QTableWidgetItem(entry.address)
        self.table.setItem(row, COL_ADDRESS, address_item)

        size_item = QTableWidgetItem(entry.display_size)
        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL_SIZE, size_item)

        md5_item = QTableWidgetItem(entry.md5 or "-")
        md5_item.setFlags(md5_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL_MD5, md5_item)

        status_item = QTableWidgetItem("Missing!" if entry.missing else "OK")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if entry.missing:
            status_item.setForeground(Qt.GlobalColor.red)
        self.table.setItem(row, COL_STATUS, status_item)

    def _entry_id_for_row(self, row: int) -> str | None:
        item = self.table.item(row, COL_ENABLED)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_entry_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._entry_id_for_row(rows[0].row())

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._device is None:
            return
        entry_id = self._entry_id_for_row(item.row())
        entry = next((f for f in self._device.firmware if f.id == entry_id), None)
        if entry is None:
            return

        if item.column() == COL_ENABLED:
            entry.enabled = item.checkState() == Qt.CheckState.Checked
        elif item.column() == COL_ADDRESS:
            candidate = item.text().strip()
            if is_valid_hex_address(candidate):
                entry.address = normalize_hex_address(candidate)
            else:
                QMessageBox.warning(self, "Invalid Address", f"'{candidate}' is not a valid hex address (e.g. 0x10000).")
                self.table.blockSignals(True)
                item.setText(entry.address)
                self.table.blockSignals(False)
                return

        self.firmware_changed.emit(self._device.id)

    # ------------------------------------------------------------------
    def _add_bin(self) -> None:
        if self._device is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Firmware BIN File(s)", "", FIRMWARE_FILE_FILTER)
        for path in paths:
            entry = FirmwareEntry(file_path=path, address="0x10000")
            entry.refresh()
            self._device.add_firmware(entry)
        if paths:
            self._reload_table()
            self.firmware_changed.emit(self._device.id)

    def _remove_selected(self) -> None:
        if self._device is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        self._device.remove_firmware(entry_id)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    def _duplicate_selected(self) -> None:
        if self._device is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        self._device.duplicate_firmware(entry_id)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    def _move_selected(self, direction: int) -> None:
        if self._device is None:
            return
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        self._device.move_firmware(entry_id, direction)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    def _import_folder(self) -> None:
        if self._device is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Select Firmware Folder")
        if not folder:
            return
        entries = scan_firmware_folder(folder)
        if not entries:
            QMessageBox.information(self, "No Firmware Found", "No .bin files were found in that folder.")
            return
        self._device.firmware.extend(entries)
        self._reload_table()
        self.firmware_changed.emit(self._device.id)

    # ------------------------------------------------------------------
    # Drag & drop support
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._device is None:
            return
        added_any = False
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if not local_path:
                continue
            if os.path.isdir(local_path):
                for entry in scan_firmware_folder(local_path):
                    self._device.add_firmware(entry)
                    added_any = True
            elif local_path.lower().endswith(".bin"):
                entry = FirmwareEntry(file_path=local_path, address="0x10000")
                entry.refresh()
                self._device.add_firmware(entry)
                added_any = True
        if added_any:
            self._reload_table()
            self.firmware_changed.emit(self._device.id)
        event.acceptProposedAction()
