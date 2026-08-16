"""
serial_monitor.py
==================
Stand-alone Serial Monitor windows, independent of the flashing pipeline.
Unlike the "View Log" console (which only ever shows esptool's own
output for one flash attempt), a Serial Monitor opens a live, two-way
serial connection to a board's regular (post-boot) UART output -- the
same job as the Arduino IDE's or PlatformIO's serial monitor.

Any number of these can be open at once (one per COM port, tracked by
MainWindow in a dict keyed by port name), each with its own baud rate,
auto-scroll/pause/search/copy/save controls mirroring LiveConsoleWidget,
plus a line to send text back to the device.

Locking / validation around this window is intentionally handled by the
*caller* (MainWindow + validator.py):
  - MainWindow refuses to open a monitor for a port that is currently
    mid-upload.
  - validate_devices() refuses to start an upload for a device whose port
    currently has a connected Serial Monitor open, and tells the user to
    close it first.
This module itself only owns the serial connection lifecycle and the
read/write UI.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import serial

from app.ui.widgets import make_scrollable
from app.utilities.constants import (
    BAUD_RATES,
    DEFAULT_SERIAL_MONITOR_BAUD,
    LIVE_LOG_MAX_LINES,
    SERIAL_MONITOR_LINE_ENDINGS,
)
from app.utilities.helpers import safe_filename, timestamp_now

_LINE_ENDING_BYTES = {
    "None": b"",
    "\\n (LF)": b"\n",
    "\\r\\n (CRLF)": b"\r\n",
    "\\r (CR)": b"\r",
}


class _SerialReaderThread(QThread):
    """Owns the actual pyserial connection on a background thread so the
    GUI thread never blocks waiting on I/O."""

    data_received = Signal(str)
    error_occurred = Signal(str)
    connection_opened = Signal()

    def __init__(self, port: str, baud: int, parent=None) -> None:
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self._serial: serial.Serial | None = None
        self._running = False
        self._write_lock = threading.Lock()
        self._pending_writes: list[bytes] = []

    def run(self) -> None:  # noqa: D102 - QThread override
        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=0.2)
        except Exception as exc:  # noqa: BLE001 - surface every failure to the UI
            self.error_occurred.emit(str(exc))
            return

        self._running = True
        self.connection_opened.emit()
        while self._running:
            try:
                with self._write_lock:
                    pending, self._pending_writes = self._pending_writes, []
                for chunk in pending:
                    self._serial.write(chunk)
                data = self._serial.read(4096)
                if data:
                    self.data_received.emit(data.decode("utf-8", errors="replace"))
            except Exception as exc:  # noqa: BLE001 - e.g. device unplugged mid-session
                self.error_occurred.emit(str(exc))
                break
        try:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
        except Exception:  # noqa: BLE001 - best-effort cleanup only
            pass

    def write(self, data: bytes) -> None:
        with self._write_lock:
            self._pending_writes.append(data)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)


class SerialMonitorWidget(QWidget):
    """One Serial Monitor window, bound to a single serial port for its
    whole lifetime (create a new one to watch a different port)."""

    closed = Signal(str)  # emits the port name when the window is closed

    def __init__(self, port: str, baud: int = DEFAULT_SERIAL_MONITOR_BAUD, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.port = port
        self._reader: _SerialReaderThread | None = None
        self._paused = False
        self._pending_lines: list[str] = []

        self.setWindowTitle(f"Serial Monitor — {port}")
        self.resize(760, 480)

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(f"Port: {port}"))
        top_row.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setCurrentText(str(baud))
        top_row.addWidget(self.baud_combo)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._toggle_connection)
        top_row.addWidget(self.connect_button)
        self.connection_status = QLabel("Disconnected")
        self._set_status_style(connected=False)
        top_row.addWidget(self.connection_status)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        toolbar_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
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
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.text_edit, 1)

        send_row = QHBoxLayout()
        self.send_edit = QLineEdit()
        self.send_edit.setPlaceholderText("Type to send to the device, then press Enter...")
        self.send_edit.returnPressed.connect(self._send)
        self.line_ending_combo = QComboBox()
        self.line_ending_combo.addItems(SERIAL_MONITOR_LINE_ENDINGS)
        self.line_ending_combo.setCurrentIndex(1)  # "\n (LF)" by default
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send)
        send_row.addWidget(self.send_edit, 1)
        send_row.addWidget(self.line_ending_combo)
        send_row.addWidget(self.send_button)
        layout.addLayout(send_row)

        self._set_connected_controls(False)

    # ------------------------------------------------------------------
    def is_connected(self) -> bool:
        return self._reader is not None

    def _set_status_style(self, connected: bool) -> None:
        color = "#2f9e44" if connected else "#e03131"
        self.connection_status.setText("Connected" if connected else "Disconnected")
        self.connection_status.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _set_connected_controls(self, connected: bool) -> None:
        self.baud_combo.setEnabled(not connected)
        self.send_edit.setEnabled(connected)
        self.send_button.setEnabled(connected)
        self.line_ending_combo.setEnabled(connected)

    # ------------------------------------------------------------------
    def _toggle_connection(self) -> None:
        if self._reader is not None:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        try:
            baud = int(self.baud_combo.currentText().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid Baud Rate", "Enter a numeric baud rate.")
            return

        self.connect_button.setEnabled(False)
        self.connect_button.setText("Connecting...")

        reader = _SerialReaderThread(self.port, baud, self)
        reader.data_received.connect(self._on_data)
        reader.error_occurred.connect(self._on_error)
        reader.connection_opened.connect(self._on_connected)
        reader.finished.connect(self._on_reader_finished)
        self._reader = reader
        reader.start()

    def _on_connected(self) -> None:
        self._set_status_style(connected=True)
        self.connect_button.setText("Disconnect")
        self.connect_button.setEnabled(True)
        self._set_connected_controls(True)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "Serial Monitor", f"Serial error on {self.port}:\n{message}")

    def _on_reader_finished(self) -> None:
        # Covers both a clean Disconnect and the thread exiting on its own
        # after a read/write error (device unplugged, port stolen, etc.).
        self._reader = None
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Connect")
        self._set_status_style(connected=False)
        self._set_connected_controls(False)

    def _disconnect(self) -> None:
        if self._reader is not None:
            self.connect_button.setEnabled(False)
            self.connect_button.setText("Disconnecting...")
            self._reader.stop()

    # ------------------------------------------------------------------
    def _on_data(self, text: str) -> None:
        if self._paused:
            self._pending_lines.append(text)
            return
        self._write_text(text)

    def _write_text(self, text: str) -> None:
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if self.autoscroll_check.isChecked():
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText("Resume" if self._paused else "Pause")
        if not self._paused and self._pending_lines:
            for text in self._pending_lines:
                self._write_text(text)
            self._pending_lines.clear()

    def _send(self) -> None:
        if self._reader is None:
            return
        text = self.send_edit.text()
        ending = _LINE_ENDING_BYTES.get(self.line_ending_combo.currentText(), b"")
        self._reader.write(text.encode("utf-8", errors="replace") + ending)
        self.send_edit.clear()

    def _on_search(self) -> None:
        term = self.search_box.text()
        if not term:
            return
        found = self.text_edit.find(term)
        if not found:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor)
            if not self.text_edit.find(term):
                QMessageBox.information(self, "Search", f"'{term}' not found in this session.")

    def _copy_all(self) -> None:
        self.text_edit.selectAll()
        self.text_edit.copy()
        cursor = self.text_edit.textCursor()
        cursor.clearSelection()
        self.text_edit.setTextCursor(cursor)

    def _save_log(self) -> None:
        default_name = f"{safe_filename(self.port)}_{timestamp_now().replace(':', '-').replace(' ', '_')}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Serial Log", default_name, "Log Files (*.log);;Text Files (*.txt)",
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

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        self.closed.emit(self.port)
        event.accept()
