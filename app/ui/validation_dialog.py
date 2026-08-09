"""
validation_dialog.py
=====================
Modal dialog shown before any upload begins, listing every ERROR and
WARNING found by flash_engine.validator. Errors block the upload;
warnings can be acknowledged and proceeded past.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from app.flash_engine.validator import Severity, ValidationReport


class ValidationReportDialog(QDialog):
    def __init__(self, report: ValidationReport, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pre-Upload Validation Report")
        self.resize(650, 400)
        self.report = report

        layout = QVBoxLayout(self)

        error_count = sum(1 for i in report.issues if i.severity == Severity.ERROR)
        warning_count = sum(1 for i in report.issues if i.severity == Severity.WARNING)
        summary = QLabel(f"<b>{error_count} error(s), {warning_count} warning(s) found.</b>")
        layout.addWidget(summary)

        table = QTableWidget(len(report.issues), 3)
        table.setHorizontalHeaderLabels(["Severity", "Device", "Message"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, issue in enumerate(report.issues):
            severity_item = QTableWidgetItem(issue.severity.value)
            if issue.severity == Severity.ERROR:
                severity_item.setForeground(QColor("#e03131"))
            else:
                severity_item.setForeground(QColor("#e0a300"))
            table.setItem(row, 0, severity_item)
            table.setItem(row, 1, QTableWidgetItem(issue.device_name))
            table.setItem(row, 2, QTableWidgetItem(issue.message))
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)

        if report.has_errors:
            note = QLabel("Errors must be resolved before uploading. This upload has been blocked.")
            note.setStyleSheet("color: #e03131; font-weight: 600;")
            layout.addWidget(note)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            buttons.accepted.connect(self.reject)
        else:
            note = QLabel("No blocking errors. You may proceed, or cancel to review warnings first.")
            layout.addWidget(note)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Proceed With Upload")
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
