"""
batch_edit_dialog.py
=====================
Lets the user change one setting (baud rate, flash mode, erase-before-
upload, etc.) across ALL devices, or just the currently selected ones,
in a single action — e.g. "set baud rate to 115200 for all devices".
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.ui.widgets import make_scrollable
from app.utilities.constants import BAUD_RATES, FLASH_FREQUENCIES, FLASH_MODES, FLASH_SIZES, SUPPORTED_CHIPS

_FIELDS = {
    "Upload Speed (baud rate)": ("baud_rate", "combo", [str(b) for b in BAUD_RATES]),
    "Chip Type": ("chip_type", "combo", SUPPORTED_CHIPS),
    "Flash Mode": ("flash_mode", "combo", FLASH_MODES),
    "Flash Frequency": ("flash_frequency", "combo", FLASH_FREQUENCIES),
    "Flash Size": ("flash_size", "combo", FLASH_SIZES),
    "Erase Before Upload": ("erase_before_upload", "bool", None),
    "Reset After Upload": ("reset_after_upload", "bool", None),
    "Compression": ("compression", "bool", None),
    "Stub Loader": ("stub_loader", "bool", None),
}


class BatchEditDialog(QDialog):
    """After exec()==Accepted, read .selected_field() and .selected_value()."""

    def __init__(self, selected_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Edit Devices")
        self.resize(420, 200)

        outer_layout = QVBoxLayout(self)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(f"Apply a setting to devices ({selected_count} currently selected)."))

        form = QFormLayout()
        self.field_combo = QComboBox()
        self.field_combo.addItems(list(_FIELDS.keys()))
        self.field_combo.currentTextChanged.connect(self._on_field_changed)
        form.addRow("Setting:", self.field_combo)

        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["All devices", "Selected devices only"])
        form.addRow("Apply to:", self.scope_combo)

        self.value_stack = QStackedWidget()
        self._combo_widget = QComboBox()
        self._bool_widget = QCheckBox("Enabled")
        self.value_stack.addWidget(self._combo_widget)
        self.value_stack.addWidget(self._bool_widget)
        form.addRow("New Value:", self.value_stack)

        layout.addLayout(form)

        outer_layout.addWidget(make_scrollable(content), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

        self._on_field_changed(self.field_combo.currentText())

    def _on_field_changed(self, field_label: str) -> None:
        _, kind, options = _FIELDS[field_label]
        if kind == "combo":
            self._combo_widget.clear()
            self._combo_widget.addItems(options)
            self.value_stack.setCurrentWidget(self._combo_widget)
        else:
            self.value_stack.setCurrentWidget(self._bool_widget)

    def apply_to_all(self) -> bool:
        return self.scope_combo.currentIndex() == 0

    def selected_field(self) -> str:
        return _FIELDS[self.field_combo.currentText()][0]

    def selected_value(self):
        field_label = self.field_combo.currentText()
        _, kind, _ = _FIELDS[field_label]
        if kind == "bool":
            return self._bool_widget.isChecked()
        text = self._combo_widget.currentText()
        if field_label == "Upload Speed (baud rate)":
            return int(text)
        return text
