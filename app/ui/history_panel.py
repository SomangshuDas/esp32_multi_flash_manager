"""
history_panel.py
=================
Displays the running log of flash attempts (date/time/device/firmware/
duration/result) and offers a CSV export button, for traceability on the
manufacturing floor.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.models.history_model import HistoryEntry, export_history_csv
from app.ui.widgets import fit_table_columns, make_scrollable, prepare_table_for_full_content


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

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Time", "Device", "Port", "Firmware", "Duration (s)", "Result"]
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
            entry.firmware_summary, f"{entry.duration_seconds:.1f}", entry.result,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if entry.result == "Failed":
                item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, col, item)
        fit_table_columns(self.table)
        self.table.scrollToBottom()

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
