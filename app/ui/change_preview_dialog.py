"""
change_preview_dialog.py
==========================
Reusable "N device(s) will change" confirmation step shown between a
batch-mutation dialog's OK and the actual mutation, for both Batch Edit
and Assign Firmware Set to Devices (see ROADMAP.md's "Diff / preview step
for Batch Edit and Assign Firmware Set" entry). Modeled on
BatchProvisionDialog's confirmation-gate pattern
(app/ui/provision_confirm_dialog.py's confirm_irreversible_burn), but
review-only: a read-only before/after table plus Apply/Cancel, with no
live progress of its own -- the actual mutation still happens the normal
way (DeviceController.apply_to_selected / apply_firmware_to_devices /
add_tag_to_devices) only after this dialog is accepted.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.ui.widgets import fit_table_columns, make_scrollable, prepare_table_for_full_content


class ChangePreviewDialog(QDialog):
    """Shows a read-only "Device | From | To" table for a pending batch
    mutation and asks for a final Apply/Cancel confirmation.

    `changes` is a list of (device_id, device_name, old_value, new_value)
    tuples, as produced by DeviceController.preview_field_change() /
    preview_tag_addition() / preview_firmware_assignment() -- rows where
    old == new are expected to already be filtered out by the caller, so
    every row shown here is a real, actionable change.
    """

    def __init__(self, title: str, changes: list[tuple[str, str, str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(650, 400)

        outer_layout = QVBoxLayout(self)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        summary = QLabel(f"<b>{len(changes)} device(s) will change:</b>")
        layout.addWidget(summary)

        table = QTableWidget(len(changes), 3)
        table.setHorizontalHeaderLabels(["Device", "From", "To"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (_device_id, name, old, new) in enumerate(changes):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(old))
            table.setItem(row, 2, QTableWidgetItem(new))
        prepare_table_for_full_content(table)
        fit_table_columns(table, min_widths={0: 130, 1: 220, 2: 220})
        table.setMinimumHeight(120)
        layout.addWidget(table, 1)

        note = QLabel("Review the changes above, then Apply to proceed or Cancel to make no changes.")
        note.setWordWrap(True)
        layout.addWidget(note)

        outer_layout.addWidget(make_scrollable(content), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)
