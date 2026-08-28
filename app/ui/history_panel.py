"""
history_panel.py
=================
Displays the running log of flash attempts (date/time/device/firmware/
duration/result), lets each successfully-flashed device be marked Pass/Fail
after physical QC, and offers search/filtering plus a CSV export button,
for traceability on the manufacturing floor.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from app.models.history_model import HistoryEntry, export_history_csv
from app.ui.widgets import fit_table_columns, make_scrollable, prepare_table_for_full_content
from app.utilities.constants import QC_STATUS_COLORS, QC_STATUS_OPTIONS, STATUS_COMPLETED

COL_DATE = 0
COL_TIME = 1
COL_DEVICE = 2
COL_PORT = 3
COL_MAC = 4
COL_FIRMWARE = 5
COL_DURATION = 6
COL_RESULT = 7
COL_QC = 8

_RESULT_FILTER_ALL = "All Results"
_QC_FILTER_ALL = "All QC Statuses"


class HistoryPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[HistoryEntry] = []

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        layout = QVBoxLayout(content)

        toolbar = QHBoxLayout()
        self.export_button = QPushButton("Export CSV...")
        self.export_button.clicked.connect(self._export_csv)
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self._clear)
        toolbar.addWidget(self.export_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        # ---- Search & filtering (device, MAC, date range, result, QC) ----
        filter_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by device name, port, or MAC address...")
        self.search_box.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_box, 1)

        self.result_filter_combo = QComboBox()
        self.result_filter_combo.addItem(_RESULT_FILTER_ALL)
        self.result_filter_combo.addItems(["Completed", "Failed", "Cancelled"])
        self.result_filter_combo.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.result_filter_combo)

        self.qc_filter_combo = QComboBox()
        self.qc_filter_combo.addItem(_QC_FILTER_ALL)
        self.qc_filter_combo.addItems(QC_STATUS_OPTIONS)
        self.qc_filter_combo.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.qc_filter_combo)

        filter_row.addWidget(QLabel("From:"))
        self.date_from_edit = QDateEdit()
        self.date_from_edit.setCalendarPopup(True)
        self.date_from_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_from_edit.setDate(self.date_from_edit.minimumDate())
        self.date_from_edit.dateChanged.connect(self._apply_filters)
        filter_row.addWidget(self.date_from_edit)

        filter_row.addWidget(QLabel("To:"))
        self.date_to_edit = QDateEdit()
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_to_edit.setDate(self.date_to_edit.maximumDate())
        self.date_to_edit.dateChanged.connect(self._apply_filters)
        filter_row.addWidget(self.date_to_edit)

        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        filter_row.addWidget(self.clear_filters_button)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Time", "Device", "Port", "MAC Address", "Firmware",
             "Duration (s)", "Result", "QC Status"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Columns are never stretched/shrunk to fit the viewport - long
        # device/firmware names always get their full width, and the
        # table's own horizontal scrollbar takes over once that's wider
        # than the panel instead of Qt eliding any cell's text.
        prepare_table_for_full_content(self.table)
        self.table.setMinimumHeight(100)
        layout.addWidget(self.table, 1)

        outer_layout.addWidget(make_scrollable(content))

    def add_entry(self, entry: HistoryEntry) -> None:
        self._entries.append(entry)
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            entry.date, entry.time, entry.device_name, entry.com_port,
            entry.mac_address or "-", entry.firmware_summary,
            f"{entry.duration_seconds:.1f}", entry.result,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if entry.result == "Failed":
                item.setForeground(Qt.GlobalColor.red)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

        # QC Verification: only a device that flashed successfully can
        # meaningfully be marked Pass/Fail on the bench -- a run that never
        # completed has nothing to QC yet, so the combo stays disabled
        # (and stuck at "Not Tested") for those rows.
        qc_combo = QComboBox()
        qc_combo.addItems(QC_STATUS_OPTIONS)
        qc_combo.setCurrentText(entry.qc_status)
        qc_combo.setEnabled(entry.result == STATUS_COMPLETED)
        qc_combo.currentTextChanged.connect(lambda status, e=entry, c=qc_combo: self._on_qc_changed(e, status, c))
        self._style_qc_combo(qc_combo, entry.qc_status)
        self.table.setCellWidget(row, COL_QC, qc_combo)

        fit_table_columns(self.table)
        self.table.scrollToBottom()
        self._apply_filters()

    def _style_qc_combo(self, combo: QComboBox, status: str) -> None:
        color = QC_STATUS_COLORS.get(status, "#8a8f98")
        combo.setStyleSheet(f"QComboBox {{ color: {color}; font-weight: 600; }}")

    def _on_qc_changed(self, entry: HistoryEntry, status: str, combo: QComboBox) -> None:
        entry.qc_status = status
        self._style_qc_combo(combo, status)

    # ------------------------------------------------------------------
    # Search & filtering
    # ------------------------------------------------------------------
    def _clear_filters(self) -> None:
        self.search_box.clear()
        self.result_filter_combo.setCurrentIndex(0)
        self.qc_filter_combo.setCurrentIndex(0)
        self.date_from_edit.setDate(self.date_from_edit.minimumDate())
        self.date_to_edit.setDate(self.date_to_edit.maximumDate())

    def _apply_filters(self, *_args) -> None:
        query = self.search_box.text().strip().lower()
        result_filter = self.result_filter_combo.currentText()
        qc_filter = self.qc_filter_combo.currentText()
        date_from = self.date_from_edit.date().toPython()
        date_to = self.date_to_edit.date().toPython()
        has_date_range = date_from != self.date_from_edit.minimumDate().toPython() or \
            date_to != self.date_to_edit.maximumDate().toPython()

        for row, entry in enumerate(self._entries):
            visible = True
            if query and query not in entry.device_name.lower() \
                    and query not in entry.com_port.lower() \
                    and query not in entry.mac_address.lower():
                visible = False
            if visible and result_filter != _RESULT_FILTER_ALL and entry.result != result_filter:
                visible = False
            if visible and qc_filter != _QC_FILTER_ALL and entry.qc_status != qc_filter:
                visible = False
            if visible and has_date_range:
                try:
                    entry_date = datetime.strptime(entry.date, "%Y-%m-%d").date()
                    if not (date_from <= entry_date <= date_to):
                        visible = False
                except ValueError:
                    pass
            self.table.setRowHidden(row, not visible)

    def _export_csv(self) -> None:
        if not self._entries:
            QMessageBox.information(self, "Export CSV", "There is no history to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export History", "flash_history.csv", "CSV Files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            export_history_csv(self._entries, path)
            QMessageBox.information(self, "Export CSV", f"History exported to:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export history:\n{exc}")

    def _clear(self) -> None:
        self._entries.clear()
        self.table.setRowCount(0)
