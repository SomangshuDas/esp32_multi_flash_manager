"""
provision_dialog.py
=====================
"Provision Device (Burn eFuses)..." dialog, opened from
SecuritySettingsWidget for the currently selected device. Runs pre-flight
validation (missing key files, no chip selected, etc. -- see
security_manager.validate_security_settings), then -- only after the user
explicitly confirms via ProvisionConfirmDialog -- drives a ProvisionWorker
QThread that generates any requested keys and burns the requested eFuses,
streaming its raw output live the same way the main Upload flow's Live
Output console does.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.flash_engine.security_manager import validate_security_settings
from app.models.device_model import DeviceConfig
from app.ui.provision_confirm_dialog import confirm_irreversible_burn
from app.utilities.constants import STATUS_COLORS, STATUS_WAITING
from app.workers.security_worker import ProvisionWorker


class ProvisionDialog(QDialog):
    def __init__(self, device: DeviceConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Provision Device — {device.name}")
        self.resize(680, 460)
        self._device = device
        self._worker: ProvisionWorker | None = None

        layout = QVBoxLayout(self)

        status_row = QVBoxLayout()
        self.status_label = QLabel(STATUS_WAITING)
        self.status_label.setStyleSheet(f"font-weight: 600; color: {STATUS_COLORS.get(STATUS_WAITING)};")
        status_row.addWidget(self.status_label)
        layout.addLayout(status_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log_view, 1)

        button_row = QVBoxLayout()
        self.start_button = QPushButton("Validate && Provision...")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._on_start_clicked)
        button_row.addWidget(self.start_button)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        self.close_buttons = buttons
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_view.setTextCursor(cursor)

    def _set_status(self, status: str) -> None:
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"font-weight: 600; color: {STATUS_COLORS.get(status, '#8a8f98')};")

    # ------------------------------------------------------------------
    def _on_start_clicked(self) -> None:
        report = validate_security_settings(self._device)
        if report.has_errors:
            lines = "\n".join(f"- {i.message}" for i in report.issues if i.is_error)
            QMessageBox.critical(self, "Cannot Provision", f"Resolve the following before provisioning:\n\n{lines}")
            return

        summary_lines = []
        sec = self._device.security
        if sec.enable_flash_encryption:
            key_desc = "a newly generated key" if sec.key_source == "generate" else sec.flash_encryption_key_path
            summary_lines.append(
                f"Burn Flash Encryption key ({key_desc}) to device on {self._device.com_port} ({self._device.chip_type})"
            )
        if sec.enable_secure_boot:
            key_desc = "a newly generated key" if sec.key_source == "generate" else sec.secure_boot_key_path
            summary_lines.append(
                f"Burn Secure Boot V{sec.secure_boot_version} key digest ({key_desc}) to device on "
                f"{self._device.com_port} ({self._device.chip_type})"
            )

        if not confirm_irreversible_burn(self, summary_lines):
            return

        self.start_button.setEnabled(False)
        self.log_view.clear()
        self._set_status("Starting")

        self._worker = ProvisionWorker(self._device)
        self._worker.status_changed.connect(lambda _id, status: self._set_status(status))
        self._worker.log_line.connect(lambda _id, line: self._append_log(line))
        self._worker.finished_provision.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, _device_id: str, success: bool, message: str, _duration: float) -> None:
        self.start_button.setEnabled(True)
        if success:
            QMessageBox.information(self, "Provisioning Complete", message)
        else:
            QMessageBox.critical(self, "Provisioning Failed", message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._worker is not None and self._worker.isRunning():
            proceed = QMessageBox.question(
                self, "Provisioning In Progress",
                "A provisioning operation is still running. Closing this window will cancel it. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.request_cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
