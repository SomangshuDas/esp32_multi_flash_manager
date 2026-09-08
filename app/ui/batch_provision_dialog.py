"""
batch_provision_dialog.py
==========================
"Provision Devices (Batch)..." dialog -- the multi-device counterpart of
app/ui/provision_dialog.py. Runs the same pre-flight validation
(security_manager.validate_security_settings) on EVERY candidate device,
drops any device that isn't configured for provisioning or that fails
validation (with the reason shown inline), then -- only after a single
explicit confirmation covering the whole batch (see
provision_confirm_dialog.confirm_irreversible_burn) -- drives a
ProvisionController that burns eFuses on up to
app.utilities.app_settings.get_max_parallel_provisions() devices at once,
queuing the rest, with a live per-device status table and a combined,
device-tagged log console.

Before this dialog existed, provisioning a batch of devices meant opening
ProvisionDialog once per device and repeating the confirm-and-burn flow
by hand for each one.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.provision_controller import ProvisionController
from app.flash_engine.security_manager import validate_security_settings
from app.models.device_model import DeviceConfig
from app.ui.provision_confirm_dialog import confirm_irreversible_burn
from app.utilities.constants import STATUS_COLORS, STATUS_WAITING


class BatchProvisionDialog(QDialog):
    def __init__(self, devices: list[DeviceConfig], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Provision Devices (Batch)")
        self.resize(760, 560)
        self._controller = ProvisionController(self)
        self._controller.device_status_changed.connect(self._on_status_changed)
        self._controller.device_log_line.connect(self._on_log_line)
        self._controller.device_finished.connect(self._on_device_finished)
        self._controller.batch_finished.connect(self._on_batch_finished)

        # Pre-flight: only devices that actually opted into Flash
        # Encryption and/or Secure Boot are provisioning candidates at
        # all; the rest are silently excluded (they simply have nothing
        # to burn). Of those candidates, only ones that pass
        # validate_security_settings are eligible to run -- the others
        # are shown, disabled, with their validation error as the reason.
        self._eligible: list[DeviceConfig] = []
        self._skip_reasons: dict[str, str] = {}
        for device in devices:
            sec = device.security
            if not (sec.enable_flash_encryption or sec.enable_secure_boot):
                continue
            report = validate_security_settings(device)
            if report.has_errors:
                reasons = "; ".join(i.message for i in report.issues if i.is_error)
                self._skip_reasons[device.id] = reasons
            else:
                self._eligible.append(device)

        layout = QVBoxLayout(self)

        summary = QLabel(self._summary_text())
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Device", "Port", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._row_for_device: dict[str, int] = {}
        self._populate_table(devices)
        layout.addWidget(self.table, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.log_view.setPlaceholderText("Live output for every device appears here, prefixed by device name.")
        layout.addWidget(self.log_view, 1)

        button_row = QVBoxLayout()
        self.start_button = QPushButton(f"Validate && Provision {len(self._eligible)} Device(s)...")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setEnabled(bool(self._eligible))
        self.start_button.clicked.connect(self._on_start_clicked)
        button_row.addWidget(self.start_button)
        self.cancel_all_button = QPushButton("Cancel All")
        self.cancel_all_button.setEnabled(False)
        self.cancel_all_button.clicked.connect(self._controller.cancel_all)
        button_row.addWidget(self.cancel_all_button)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _summary_text(self) -> str:
        lines = [
            f"{len(self._eligible)} device(s) are configured for provisioning and passed pre-flight validation."
        ]
        if self._skip_reasons:
            lines.append(f"{len(self._skip_reasons)} device(s) will be skipped (see table below).")
        if not self._eligible:
            lines.append("Nothing to provision -- select devices with Flash Encryption and/or Secure Boot enabled.")
        return " ".join(lines)

    def _populate_table(self, devices: list[DeviceConfig]) -> None:
        rows = [d for d in devices if d.id in {e.id for e in self._eligible} or d.id in self._skip_reasons]
        self.table.setRowCount(len(rows))
        for row, device in enumerate(rows):
            self._row_for_device[device.id] = row
            self.table.setItem(row, 0, QTableWidgetItem(device.name))
            self.table.setItem(row, 1, QTableWidgetItem(device.com_port or "—"))
            if device.id in self._skip_reasons:
                status_item = QTableWidgetItem(f"Skipped: {self._skip_reasons[device.id]}")
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item = QTableWidgetItem(STATUS_WAITING)
            self.table.setItem(row, 2, status_item)

    def _set_row_status(self, device_id: str, status: str) -> None:
        row = self._row_for_device.get(device_id)
        if row is None:
            return
        item = self.table.item(row, 2)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, 2, item)
        item.setText(status)
        color = STATUS_COLORS.get(status)
        if color:
            from PySide6.QtGui import QColor

            item.setForeground(QColor(color))

    # ------------------------------------------------------------------
    def _on_start_clicked(self) -> None:
        if not self._eligible:
            return

        summary_lines = []
        for device in self._eligible:
            sec = device.security
            if sec.enable_flash_encryption:
                key_desc = "a newly generated key" if sec.key_source == "generate" else sec.flash_encryption_key_path
                summary_lines.append(
                    f"{device.name} ({device.com_port}): burn Flash Encryption key ({key_desc})"
                )
            if sec.enable_secure_boot:
                key_desc = "a newly generated key" if sec.key_source == "generate" else sec.secure_boot_key_path
                summary_lines.append(
                    f"{device.name} ({device.com_port}): burn Secure Boot V{sec.secure_boot_version} "
                    f"key digest ({key_desc})"
                )

        show_backup_reminder = any(
            d.security.key_source == "generate"
            and (d.security.enable_flash_encryption or d.security.enable_secure_boot)
            for d in self._eligible
        )
        if not confirm_irreversible_burn(self, summary_lines, show_backup_reminder=show_backup_reminder):
            return

        self.start_button.setEnabled(False)
        self.cancel_all_button.setEnabled(True)
        self.log_view.clear()
        self._controller.start_batch(self._eligible)

    def _on_status_changed(self, device_id: str, status: str) -> None:
        self._set_row_status(device_id, status)

    def _on_log_line(self, device_id: str, line: str) -> None:
        row = self._row_for_device.get(device_id)
        name = self.table.item(row, 0).text() if row is not None else device_id
        self.log_view.appendPlainText(f"[{name}] {line}")
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_view.setTextCursor(cursor)

    def _on_device_finished(self, device_id: str, success: bool, message: str, _duration: float) -> None:
        del success, message  # status text already reflects the outcome
        del device_id

    def _on_batch_finished(self, succeeded: int, failed: int) -> None:
        self.cancel_all_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.start_button.setText(f"Validate && Provision {len(self._eligible)} Device(s)...")
        QMessageBox.information(
            self, "Batch Provisioning Finished",
            f"{succeeded} device(s) provisioned successfully, {failed} failed or were cancelled.",
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._controller.any_busy():
            proceed = QMessageBox.question(
                self, "Provisioning In Progress",
                "Devices are still being provisioned. Closing this window will cancel any still running "
                "or queued. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._controller.cancel_all()
        super().closeEvent(event)
