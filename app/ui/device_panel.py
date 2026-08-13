"""
device_panel.py
================
The central device table: one row per configured ESP32, each with its
own live status badge, progress bar, elapsed/ETA/speed readouts, and a
"View Log" button. Also hosts the device-list toolbar (add/remove/
duplicate/search) and the multi-select context menu used for batch
operations and parallel upload/cancel.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.device_model import DeviceConfig
from app.ui.widgets import StatusBadge, fit_table_columns, make_scrollable
from app.utilities.constants import ACTIVE_STATUSES
from app.utilities.helpers import human_readable_duration

COL_NAME = 0
COL_PORT = 1
COL_CHIP = 2
COL_STATUS = 3
COL_PROGRESS = 4
COL_ELAPSED = 5
COL_ETA = 6
COL_SPEED = 7
COL_LOG = 8


class DevicePanel(QWidget):
    """
    Signals
    -------
    selection_changed(str | None)   - device_id of the (first) selected row
    view_log_requested(str)         - device_id
    add_device_requested()
    remove_devices_requested(list)  - list[device_id]
    duplicate_devices_requested(list)
    upload_requested(list)          - list[device_id] to upload
    cancel_requested(list)          - list[device_id] to cancel
    """

    selection_changed = Signal(object)
    view_log_requested = Signal(str)
    add_device_requested = Signal()
    remove_devices_requested = Signal(list)
    duplicate_devices_requested = Signal(list)
    upload_requested = Signal(list)
    cancel_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row_by_device_id: dict[str, int] = {}
        self._start_times: dict[str, float] = {}

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        layout = QVBoxLayout(content)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add Device")
        self.remove_button = QPushButton("Remove")
        self.duplicate_button = QPushButton("Duplicate")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by name, port, chip, or status...")

        self.add_button.clicked.connect(self.add_device_requested.emit)
        self.remove_button.clicked.connect(self._emit_remove_selected)
        self.duplicate_button.clicked.connect(self._emit_duplicate_selected)

        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.remove_button)
        toolbar.addWidget(self.duplicate_button)
        toolbar.addWidget(self.search_box, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Port", "Chip", "Status", "Progress", "Elapsed", "ETA", "Speed", ""]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Every column (including Name) is user-resizable by dragging its
        # header edge. "Interactive" is the only resize mode that allows
        # that; "Stretch" locks a column's width to whatever space is left,
        # so it's intentionally not used for any column here.
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(40)
        self._default_widths = {
            COL_NAME: 200, COL_PORT: 130, COL_CHIP: 90, COL_STATUS: 110,
            COL_PROGRESS: 150, COL_ELAPSED: 80, COL_ETA: 80, COL_SPEED: 90,
            COL_LOG: 90,
        }
        for column, width in self._default_widths.items():
            self.table.setColumnWidth(column, width)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setMinimumHeight(120)
        layout.addWidget(self.table, 1)

        outer_layout.addWidget(make_scrollable(content))

    # ------------------------------------------------------------------
    def rebuild(self, devices: list[DeviceConfig]) -> None:
        """Fully rebuild the table from the given device list (e.g. project load)."""
        self.table.setRowCount(0)
        self._row_by_device_id.clear()
        for device in devices:
            self._add_row(device)
        fit_table_columns(self.table, self._default_widths)

    def _add_row(self, device: DeviceConfig) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_by_device_id[device.id] = row

        name_item = QTableWidgetItem(device.name)
        name_item.setData(Qt.ItemDataRole.UserRole, device.id)
        self.table.setItem(row, COL_NAME, name_item)
        self.table.setItem(row, COL_PORT, QTableWidgetItem(device.com_port))
        self.table.setItem(row, COL_CHIP, QTableWidgetItem(device.chip_type))

        badge = StatusBadge(device.runtime.status)
        self.table.setCellWidget(row, COL_STATUS, badge)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(device.runtime.progress_percent)
        self.table.setCellWidget(row, COL_PROGRESS, progress)

        self.table.setItem(row, COL_ELAPSED, QTableWidgetItem("-"))
        self.table.setItem(row, COL_ETA, QTableWidgetItem("-"))
        self.table.setItem(row, COL_SPEED, QTableWidgetItem("-"))

        log_button = QPushButton("View Log")
        log_button.clicked.connect(lambda _checked, did=device.id: self.view_log_requested.emit(did))
        self.table.setCellWidget(row, COL_LOG, log_button)

        fit_table_columns(self.table, self._default_widths)

    def remove_device_row(self, device_id: str) -> None:
        row = self._row_by_device_id.pop(device_id, None)
        if row is None:
            return
        self.table.removeRow(row)
        # Shift down every row index greater than the removed one.
        self._row_by_device_id = {
            did: (r - 1 if r > row else r) for did, r in self._row_by_device_id.items()
        }

    def update_device_summary(self, device: DeviceConfig) -> None:
        """Refresh the static columns (name/port/chip) for one device row."""
        row = self._row_by_device_id.get(device.id)
        if row is None:
            return
        self.table.item(row, COL_NAME).setText(device.name)
        self.table.item(row, COL_PORT).setText(device.com_port)
        self.table.item(row, COL_CHIP).setText(device.chip_type)
        fit_table_columns(self.table, self._default_widths)

    # ------------------------------------------------------------------
    # Live progress updates (called by MainWindow in response to
    # FlashController signals)
    # ------------------------------------------------------------------
    def set_status(self, device_id: str, status: str) -> None:
        row = self._row_by_device_id.get(device_id)
        if row is None:
            return
        badge: StatusBadge = self.table.cellWidget(row, COL_STATUS)  # type: ignore[assignment]
        badge.set_status(status)
        if status in ACTIVE_STATUSES and device_id not in self._start_times:
            self._start_times[device_id] = time.monotonic()
        if status not in ACTIVE_STATUSES:
            self._start_times.pop(device_id, None)

    def set_progress(self, device_id: str, percent: int, address: str) -> None:
        row = self._row_by_device_id.get(device_id)
        if row is None:
            return
        progress: QProgressBar = self.table.cellWidget(row, COL_PROGRESS)  # type: ignore[assignment]
        progress.setValue(percent)

        start = self._start_times.get(device_id)
        if start is not None:
            elapsed = time.monotonic() - start
            self.table.item(row, COL_ELAPSED).setText(human_readable_duration(elapsed))
            if percent > 0:
                total_estimate = elapsed / (percent / 100.0)
                remaining = max(total_estimate - elapsed, 0)
                self.table.item(row, COL_ETA).setText(human_readable_duration(remaining))

    def set_speed(self, device_id: str, kbps: float) -> None:
        row = self._row_by_device_id.get(device_id)
        if row is None:
            return
        self.table.item(row, COL_SPEED).setText(f"{kbps:,.0f} KB/s")

    def reset_progress(self, device_id: str) -> None:
        row = self._row_by_device_id.get(device_id)
        if row is None:
            return
        progress: QProgressBar = self.table.cellWidget(row, COL_PROGRESS)  # type: ignore[assignment]
        progress.setValue(0)
        self.table.item(row, COL_ELAPSED).setText("-")
        self.table.item(row, COL_ETA).setText("-")
        self.table.item(row, COL_SPEED).setText("-")
        self._start_times.pop(device_id, None)

    # ------------------------------------------------------------------
    def selected_device_ids(self) -> list[str]:
        ids: list[str] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), COL_NAME)
            if item:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _on_selection_changed(self) -> None:
        ids = self.selected_device_ids()
        self.selection_changed.emit(ids[0] if ids else None)

    def _emit_remove_selected(self) -> None:
        ids = self.selected_device_ids()
        if ids:
            self.remove_devices_requested.emit(ids)

    def _emit_duplicate_selected(self) -> None:
        ids = self.selected_device_ids()
        if ids:
            self.duplicate_devices_requested.emit(ids)

    def _show_context_menu(self, pos) -> None:
        ids = self.selected_device_ids()
        if not ids:
            return
        menu = QMenu(self)
        upload_action = menu.addAction(f"Upload Selected ({len(ids)})")
        cancel_action = menu.addAction("Cancel Selected")
        menu.addSeparator()
        duplicate_action = menu.addAction("Duplicate")
        remove_action = menu.addAction("Remove")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == upload_action:
            self.upload_requested.emit(ids)
        elif chosen == cancel_action:
            self.cancel_requested.emit(ids)
        elif chosen == duplicate_action:
            self.duplicate_devices_requested.emit(ids)
        elif chosen == remove_action:
            self.remove_devices_requested.emit(ids)

    def apply_search_filter(self, visible_ids: set[str] | None) -> None:
        """Hide rows whose device id is not in `visible_ids` (None = show all)."""
        for device_id, row in self._row_by_device_id.items():
            self.table.setRowHidden(row, visible_ids is not None and device_id not in visible_ids)
