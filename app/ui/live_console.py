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

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utilities.constants import LIVE_LOG_MAX_LINES
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

        toolbar = QHBoxLayout()
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

        toolbar.addWidget(self.search_box, 1)
        toolbar.addWidget(self.autoscroll_check)
        toolbar.addWidget(self.pause_button)
        toolbar.addWidget(self.copy_button)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.clear_button)
        layout.addLayout(toolbar)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(LIVE_LOG_MAX_LINES)
        self.text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        layout.addWidget(self.text_edit, 1)

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
        path, _ = QFileDialog.getSaveFileName(self, "Save Log", default_name, "Log Files (*.log);;Text Files (*.txt)")
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
