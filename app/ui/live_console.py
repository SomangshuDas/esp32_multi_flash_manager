"""
live_console.py
================
"View Live Output" window: shows raw esptool stdout for one device in
real time, with pause/resume, search/highlight, copy, save-to-file and
clear controls. One instance is created per device the first time the
user opens its console, then reused/reshown afterwards to preserve
scrollback.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import make_scrollable
from app.utilities.constants import LIVE_LOG_MAX_LINES, STATUS_COLORS, STATUS_WAITING
from app.utilities.helpers import safe_filename, timestamp_now


class LiveConsoleWidget(QWidget):
    """
    Embeddable live console. Used both as a standalone floating window
    (via MainWindow) and could be embedded inline if desired later.
    """

    def __init__(self, device_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.device_name = device_name
        self._paused = False
        self._pending_lines: list[str] = []
        self._line_count = 0

        self.setWindowTitle(f"Live Output — {device_name}")
        self.resize(800, 500)

        layout = QVBoxLayout(self)

        status_row = QHBoxLayout()
        self.status_label = QLabel(STATUS_WAITING)
        self.status_label.setStyleSheet(f"font-weight: 600; color: {STATUS_COLORS.get(STATUS_WAITING, '#8a8f98')};")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Waiting to start...")
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.progress_bar, 1)
        layout.addLayout(status_row)

        toolbar_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search log...")
        self.search_box.returnPressed.connect(self._on_search)
        self.autoscroll_check = QCheckBox("Auto-scroll")
        self.autoscroll_check.setChecked(True)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._copy_all)
        self.save_button = QPushButton("Save Log...")
        self.save_button.clicked.connect(self._save_log)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear)

        toolbar_row.addWidget(self.search_box, 1)
        toolbar_row.addWidget(self.autoscroll_check)
        toolbar_row.addWidget(self.pause_button)
        toolbar_row.addWidget(self.copy_button)
        toolbar_row.addWidget(self.save_button)
        toolbar_row.addWidget(self.clear_button)
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar_row)
        toolbar_scroll = make_scrollable(toolbar_widget, horizontal=True, vertical=False)
        toolbar_scroll.setMaximumHeight(toolbar_widget.sizeHint().height() + 12)
        layout.addWidget(toolbar_scroll)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(LIVE_LOG_MAX_LINES)
        self.text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        # Long esptool lines wrap to the widget width so every character is
        # always visible without needing to scroll sideways.
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.text_edit, 1)

    # ------------------------------------------------------------------
    def set_status(self, status: str) -> None:
        """Update the status pill shown above the progress bar in real time."""
        self.status_label.setText(status)
        color = STATUS_COLORS.get(status, "#8a8f98")
        self.status_label.setStyleSheet(f"font-weight: 600; color: {color};")

    def set_progress(self, percent: int, address: str) -> None:
        """Update the real-time upload progress bar for this device."""
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.progress_bar.setFormat(f"%p% — {address}" if address else "%p%")

    def start_new_run(self) -> None:
        """Reset the console (log, progress, status) for a fresh upload attempt,
        keeping the window itself open so the user doesn't lose their place."""
        self._pending_lines.clear()
        self._paused = False
        self.pause_button.setText("Pause")
        self.text_edit.clear()
        self._line_count = 0
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Waiting to start...")
        self.set_status(STATUS_WAITING)

    # ------------------------------------------------------------------
    def append_line(self, line: str) -> None:
        if self._paused:
            self._pending_lines.append(line)
            return
        self._write_line(line)

    def _write_line(self, line: str) -> None:
        self.text_edit.appendPlainText(line)
        self._line_count += 1
        if self.autoscroll_check.isChecked():
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_edit.setTextCursor(cursor)

    # ------------------------------------------------------------------
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText("Resume" if self._paused else "Pause")
        if not self._paused and self._pending_lines:
            for line in self._pending_lines:
                self._write_line(line)
            self._pending_lines.clear()

    def _on_search(self) -> None:
        term = self.search_box.text()
        if not term:
            return
        found = self.text_edit.find(term)
        if not found:
            # wrap around: move cursor to start and try again
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor)
            if not self.text_edit.find(term):
                QMessageBox.information(self, "Search", f"'{term}' not found in this log.")

    def _copy_all(self) -> None:
        self.text_edit.selectAll()
        self.text_edit.copy()
        cursor = self.text_edit.textCursor()
        cursor.clearSelection()
        self.text_edit.setTextCursor(cursor)

    def _save_log(self) -> None:
        default_name = f"{safe_filename(self.device_name)}_{timestamp_now().replace(':', '-').replace(' ', '_')}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", default_name, "Log Files (*.log);;Text Files (*.txt)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.text_edit.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save log:\n{exc}")

    def _clear(self) -> None:
        self.text_edit.clear()
        self._line_count = 0
