"""
read_device_dialog.py
=======================
"Read Flash / eFuse / Chip Info..." dialog -- a read-only inspection panel
for a single device, independent of the flash workflow (openable at any
time the device isn't mid-flash). Equivalent to Espressif's Flash Download
Tool's own read-back tab, built entirely on esptool's/espefuse's own
read-only commands (see app/workers/read_worker.py). Nothing here writes
to flash or eFuse.

Output can be saved to a file, following the same pattern as Merge Bins'
output handling (app/ui/merge_bin_dialog.py): a Settings-backed default
folder (SETTINGS_KEY_READ_DEFAULT_LOCATION) the user can override per-read
via Browse..., falling back to the user's home folder the first time.

Results are shown in two tabs: **Log** is the complete, unmodified
esptool/espefuse output (identical to every prior release of this
dialog), and **Summary** is a best-effort, human-friendly key/value
rendering of that same output produced by
app/utilities/read_output_parser.py -- e.g. "Chip Model: ESP32-D0WDQ6"
instead of scrolling through raw chip-id/flash-id/summary/
get-security-info text. The Summary tab never replaces the Log tab and
never blocks on a field it can't confidently parse -- it simply omits
that field and, if nothing at all was recognized, says so and points back
at Log.
"""

from __future__ import annotations

import time
from html import escape
from pathlib import Path

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.device_model import DeviceConfig
from app.flash_engine.security_manager import parse_security_state_from_output
from app.ui.widgets import make_scrollable
from app.utilities.app_settings import get_settings
from app.utilities.constants import (
    DEFAULT_READ_FLASH_ADDRESS,
    DEFAULT_READ_FLASH_SIZE,
    READ_MODE_CHIP_INFO,
    READ_MODE_EFUSE_SUMMARY,
    READ_MODE_FLASH_ID,
    READ_MODE_LABELS,
    READ_MODE_READ_FLASH,
    READ_MODE_SECURITY_INFO,
    SETTINGS_KEY_READ_DEFAULT_LOCATION,
)
from app.utilities.helpers import safe_filename, timestamp_now
from app.utilities.read_output_parser import parse_read_output
from app.workers.read_worker import ReadWorker

_MODES_NEEDING_OUTPUT_FILE = {READ_MODE_READ_FLASH}
_MODES_ALLOWING_OUTPUT_FILE = {READ_MODE_READ_FLASH, READ_MODE_EFUSE_SUMMARY}

_SUMMARY_PLACEHOLDER = (
    "Run an operation above to see a friendly, plain-language summary here.\n"
    "The Log tab always shows the complete, unmodified esptool/espefuse output."
)
_SUMMARY_NO_FIELDS_RECOGNIZED = (
    "Ran successfully, but no fields could be confidently parsed out of this "
    "output for a friendly summary. See the Log tab for the complete, "
    "unmodified result."
)


class ReadDeviceDialog(QDialog):
    def __init__(self, device: DeviceConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Read Flash / eFuse / Chip Info — {device.name}")
        self.resize(700, 520)
        self.settings = get_settings()
        self._device = device
        self._worker: ReadWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Read-only inspection -- nothing here writes to flash or eFuse. Runs "
            "esptool's chip-id/flash-id/get-security-info/read-flash and espefuse's summary."
        ))

        form = QFormLayout()
        self.mode_combo = QComboBox()
        for mode in (
            READ_MODE_CHIP_INFO, READ_MODE_FLASH_ID, READ_MODE_EFUSE_SUMMARY,
            READ_MODE_SECURITY_INFO, READ_MODE_READ_FLASH,
        ):
            self.mode_combo.addItem(READ_MODE_LABELS[mode], mode)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Operation:", self.mode_combo)

        self.address_edit = QLineEdit(DEFAULT_READ_FLASH_ADDRESS)
        self.size_edit = QLineEdit(DEFAULT_READ_FLASH_SIZE)
        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("Address:"))
        addr_row.addWidget(self.address_edit)
        addr_row.addWidget(QLabel("Size:"))
        addr_row.addWidget(self.size_edit)
        self.address_size_row_widget = QWidget()
        self.address_size_row_widget.setLayout(addr_row)
        form.addRow("Flash Region:", self.address_size_row_widget)

        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_button)
        self.output_row_widget = QWidget()
        self.output_row_widget.setLayout(output_row)
        form.addRow("Save To File:", self.output_row_widget)

        layout.addLayout(form)

        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        self.output_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        self.summary_view = QTextEdit()
        self.summary_view.setReadOnly(True)
        self.summary_view.setPlainText(_SUMMARY_PLACEHOLDER)

        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(self.summary_view, "Summary")
        self.result_tabs.addTab(self.output_view, "Log")
        layout.addWidget(self.result_tabs, 1)

        self._run_started_at: float = 0.0

        action_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._on_run_clicked)
        self.save_log_button = QPushButton("Save Output As Text...")
        self.save_log_button.clicked.connect(self._save_log_as_text)
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.save_log_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

        self._on_mode_changed()

    # ------------------------------------------------------------------
    def _default_output_path(self, mode: str) -> str:
        location = self.settings.value(SETTINGS_KEY_READ_DEFAULT_LOCATION, "") or str(Path.home())
        stamp = timestamp_now().replace(":", "-").replace(" ", "_")
        device_part = safe_filename(self._device.name)
        if mode == READ_MODE_READ_FLASH:
            filename = f"{device_part}_flash_read_{stamp}.bin"
        else:
            filename = f"{device_part}_efuse_summary_{stamp}.txt"
        return str(Path(location) / filename)

    def _on_mode_changed(self, *_args) -> None:
        mode = self.mode_combo.currentData()
        self.address_size_row_widget.setVisible(mode == READ_MODE_READ_FLASH)
        allow_output = mode in _MODES_ALLOWING_OUTPUT_FILE
        self.output_row_widget.setVisible(allow_output)
        if allow_output and not self.output_edit.text().strip():
            self.output_edit.setText(self._default_output_path(mode))
        self.summary_view.setPlainText(_SUMMARY_PLACEHOLDER)

    def _browse_output(self) -> None:
        mode = self.mode_combo.currentData()
        current = self.output_edit.text() or self._default_output_path(mode)
        file_filter = "Binary Files (*.bin)" if mode == READ_MODE_READ_FLASH else "Text Files (*.txt)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Read Output As", current, file_filter,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self.output_edit.setText(path)
            self.settings.setValue(SETTINGS_KEY_READ_DEFAULT_LOCATION, str(Path(path).parent))

    # ------------------------------------------------------------------
    def _on_run_clicked(self) -> None:
        mode = self.mode_combo.currentData()
        output_path = self.output_edit.text().strip() if mode in _MODES_ALLOWING_OUTPUT_FILE else ""

        if mode in _MODES_NEEDING_OUTPUT_FILE and not output_path:
            QMessageBox.warning(self, "Output File Required", "Choose a file to save the read-back data to.")
            return
        if output_path:
            parent_dir = Path(output_path).expanduser().parent
            if not parent_dir.is_dir():
                QMessageBox.warning(self, "Invalid Output Path", f"Output folder does not exist: {parent_dir}")
                return

        if not self._device.com_port:
            QMessageBox.warning(self, "No Port Selected", "This device has no serial port configured.")
            return

        self.run_button.setEnabled(False)
        self.output_view.clear()
        self.summary_view.setPlainText("Running...")
        self._run_started_at = time.monotonic()

        self._worker = ReadWorker(
            self._device, mode,
            read_address=self.address_edit.text().strip(),
            read_size=self.size_edit.text().strip(),
            output_path=output_path,
        )
        self._worker.log_line.connect(self._append_output)
        self._worker.finished_read.connect(self._on_finished)
        self._worker.start()

    def _append_output(self, line: str) -> None:
        self.output_view.appendPlainText(line)
        cursor = self.output_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_view.setTextCursor(cursor)

    def _on_finished(self, success: bool, message: str, output_path: str) -> None:
        self.run_button.setEnabled(True)
        mode = self.mode_combo.currentData()
        if success:
            note = f"\n>>> {message}"
            if output_path:
                note += f"\n>>> Saved to: {output_path}"
            self.output_view.appendPlainText(note)
            if output_path:
                self.settings.setValue(SETTINGS_KEY_READ_DEFAULT_LOCATION, str(Path(output_path).parent))
            if mode in (READ_MODE_SECURITY_INFO, READ_MODE_EFUSE_SUMMARY):
                fe_state, sb_state = parse_security_state_from_output(self.output_view.toPlainText())
                if fe_state is not None:
                    self._device.runtime.flash_encryption_detected = fe_state
                if sb_state is not None:
                    self._device.runtime.secure_boot_detected = sb_state
            self._render_summary(mode, output_path)
        else:
            self.output_view.appendPlainText(f"\n>>> FAILED: {message}")
            self.summary_view.setPlainText(f"FAILED: {message}\n\nSee the Log tab for the complete output.")
            QMessageBox.critical(self, "Read Failed", message)

    def _render_summary(self, mode: str, output_path: str) -> None:
        duration = time.monotonic() - self._run_started_at if self._run_started_at else None
        rows = parse_read_output(
            mode,
            self.output_view.toPlainText(),
            address=self.address_edit.text().strip(),
            size=self.size_edit.text().strip(),
            output_path=output_path,
            duration_seconds=duration,
        )
        if not rows:
            self.summary_view.setPlainText(_SUMMARY_NO_FIELDS_RECOGNIZED)
            return

        html_rows = "".join(
            f"<tr><td style='padding:2px 12px 2px 0; color:#888;'>{escape(label)}</td>"
            f"<td style='padding:2px 0;'><b>{escape(value)}</b></td></tr>"
            for label, value in rows
        )
        self.summary_view.setHtml(f"<table>{html_rows}</table>")

    def _save_log_as_text(self) -> None:
        default_name = f"{safe_filename(self._device.name)}_read_output_{timestamp_now().replace(':', '-').replace(' ', '_')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output", default_name, "Text Files (*.txt)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.output_view.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save output:\n{exc}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
