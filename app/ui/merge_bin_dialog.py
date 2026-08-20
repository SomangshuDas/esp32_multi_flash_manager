"""
merge_bin_dialog.py
=====================
"Merge Bins..." dialog, opened from FirmwarePanel for the currently
selected device. Lets the user pick which of the device's firmware rows
to combine into one flashable image via esptool's `merge-bin`, choose
where to save it (defaulting to the same folder as firmware.bin, per
Settings), validate before running, and decide what happens to
Firmware Settings afterwards.

On accept(), the caller (FirmwarePanel) reads:
  - merged_entry() -> a new FirmwareEntry for the just-written file
  - post_action()  -> one of the MERGE_POST_ACTION_* constants
  - source_entry_ids() -> ids of the FirmwareEntry rows that were merged,
    so the caller can de-select/remove them per post_action
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.firmware_manager.bin_merge import (
    MergeSeverity,
    firmware_bin_folder,
    run_merge,
    validate_merge_entries,
)
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.ui.widgets import fit_table_columns, make_scrollable, prepare_table_for_full_content
from app.utilities.app_settings import get_settings
from app.utilities.chip_detect import AUTO_CHIP
from app.utilities.constants import (
    DEFAULT_MERGE_OUTPUT_LOCATION,
    DEFAULT_MERGE_POST_ACTION,
    DEFAULT_MERGED_BIN_FILENAME,
    FIRMWARE_FILE_FILTER,
    MERGE_POST_ACTION_LABELS,
    MERGE_POST_ACTIONS,
    SETTINGS_KEY_MERGE_DEFAULT_FILENAME,
    SETTINGS_KEY_MERGE_DEFAULT_LOCATION,
    SETTINGS_KEY_MERGE_POST_ACTION,
)

COL_INCLUDE = 0
COL_FILE = 1
COL_ADDRESS = 2


class MergeBinDialog(QDialog):
    def __init__(self, device: DeviceConfig, supported_chips: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Merge Bins — {device.name}")
        self.resize(640, 520)
        self.settings = get_settings()
        self._device = device
        self._merged_entry: FirmwareEntry | None = None

        # merge-bin needs one concrete chip -- "auto" is meaningless offline.
        self._real_chips = [c for c in supported_chips if c != AUTO_CHIP] or [device.chip_type or "esp32"]

        outer_layout = QVBoxLayout(self)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(
            "Select the firmware rows to combine into one flashable image. "
            "Merging runs entirely offline -- no device connection is needed."
        ))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Include", "File", "Address"])
        prepare_table_for_full_content(self.table)
        self.table.setMinimumHeight(160)
        self._populate_table()
        layout.addWidget(self.table, 1)

        form = QFormLayout()
        self.chip_combo = QComboBox()
        self.chip_combo.addItems(self._real_chips)
        if device.chip_type in self._real_chips:
            self.chip_combo.setCurrentText(device.chip_type)
        form.addRow("Target Chip:", self.chip_combo)

        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setText(self._default_output_path())
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_button)
        form.addRow("Output File:", output_row)

        self.post_action_combo = QComboBox()
        for value in MERGE_POST_ACTIONS:
            self.post_action_combo.addItem(MERGE_POST_ACTION_LABELS[value], value)
        default_action = self.settings.value(SETTINGS_KEY_MERGE_POST_ACTION, DEFAULT_MERGE_POST_ACTION)
        idx = self.post_action_combo.findData(default_action)
        self.post_action_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("After Merging:", self.post_action_combo)

        layout.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        outer_layout.addWidget(make_scrollable(content), 1)

        button_row = QHBoxLayout()
        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(lambda: self._run_validation(silent_if_ok=False))
        self.merge_button = QPushButton("Merge")
        self.merge_button.setObjectName("primaryButton")
        self.merge_button.clicked.connect(self._on_merge_clicked)
        button_row.addWidget(self.validate_button)
        button_row.addWidget(self.merge_button)
        button_row.addStretch(1)
        outer_layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        outer_layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for entry in self._device.firmware:
            row = self.table.rowCount()
            self.table.insertRow(row)

            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            check_item.setCheckState(Qt.CheckState.Checked if entry.enabled else Qt.CheckState.Unchecked)
            check_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.table.setItem(row, COL_INCLUDE, check_item)

            file_item = QTableWidgetItem(entry.file_name)
            file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            file_item.setToolTip(entry.file_path)
            self.table.setItem(row, COL_FILE, file_item)

            address_item = QTableWidgetItem(entry.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, COL_ADDRESS, address_item)

        fit_table_columns(self.table, {COL_FILE: 220})

    def _selected_entries(self) -> list[FirmwareEntry]:
        selected_ids = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_INCLUDE)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_ids.add(item.data(Qt.ItemDataRole.UserRole))
        return [e for e in self._device.firmware if e.id in selected_ids]

    def _default_output_path(self) -> str:
        filename = self.settings.value(SETTINGS_KEY_MERGE_DEFAULT_FILENAME, DEFAULT_MERGED_BIN_FILENAME) or DEFAULT_MERGED_BIN_FILENAME
        location = self.settings.value(SETTINGS_KEY_MERGE_DEFAULT_LOCATION, DEFAULT_MERGE_OUTPUT_LOCATION)
        if not location:
            location = firmware_bin_folder(self._device.firmware) or str(Path.home())
        return str(Path(location) / filename)

    def _browse_output(self) -> None:
        current = self.output_edit.text() or self._default_output_path()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Merged Firmware As", current, FIRMWARE_FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self.output_edit.setText(path)

    # ------------------------------------------------------------------
    def _run_validation(self, silent_if_ok: bool) -> bool:
        """Returns True if there are no blocking errors (warnings may still
        be present -- the caller decides whether those need confirming)."""
        entries = self._selected_entries()
        report = validate_merge_entries(entries, self.chip_combo.currentText(), self.output_edit.text().strip())

        if not report.issues:
            self.status_label.setStyleSheet("color: #2f9e44;")
            self.status_label.setText("No issues found. Ready to merge.")
            if not silent_if_ok:
                QMessageBox.information(self, "Validate", "No issues found. Ready to merge.")
            return True

        lines = []
        for issue in report.issues:
            color = "#e03131" if issue.severity == MergeSeverity.ERROR else "#e0a300"
            lines.append(f"<span style='color:{color};'>[{issue.severity.value}]</span> {issue.message}")
        self.status_label.setStyleSheet("")
        self.status_label.setText("<br>".join(lines))

        if report.has_errors and not silent_if_ok:
            QMessageBox.warning(self, "Validation Errors", "Please resolve the error(s) shown below the table before merging.")
        return not report.has_errors

    def _on_merge_clicked(self) -> None:
        entries = self._selected_entries()
        chip = self.chip_combo.currentText()
        output_path = self.output_edit.text().strip()

        report = validate_merge_entries(entries, chip, output_path)
        if report.has_errors:
            self._run_validation(silent_if_ok=True)
            QMessageBox.warning(self, "Cannot Merge", "Please resolve the error(s) shown below the table before merging.")
            return
        if report.has_warnings:
            self._run_validation(silent_if_ok=True)
            proceed = QMessageBox.question(
                self, "Merge With Warnings?",
                "Some non-blocking warnings were found (see below the table). Merge anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        flash_mode = self._device.flash_mode if self._device.flash_mode != "keep" else "keep"
        flash_freq = self._device.flash_frequency if self._device.flash_frequency != "keep" else "keep"
        flash_size = self._device.flash_size if self._device.flash_size != "keep" else "keep"

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = run_merge(entries, chip, output_path, flash_mode, flash_freq, flash_size)
        finally:
            QApplication.restoreOverrideCursor()

        if not result.success:
            detail = result.error_message
            if result.output_text.strip():
                detail += "\n\n" + result.output_text.strip()[-2000:]
            QMessageBox.critical(self, "Merge Failed", detail)
            self.status_label.setStyleSheet("color: #e03131;")
            self.status_label.setText(f"Merge failed: {result.error_message}")
            return

        merged = FirmwareEntry(file_path=output_path, address="0x0", enabled=True)
        merged.refresh()
        self._merged_entry = merged
        self._source_ids = [e.id for e in entries]

        QMessageBox.information(self, "Merge Complete", f"Merged image written to:\n{output_path}")
        self.status_label.setStyleSheet("color: #2f9e44;")
        self.status_label.setText(f"Merge complete: {output_path}")
        self.accept()

    # ------------------------------------------------------------------
    def merged_entry(self) -> FirmwareEntry | None:
        return self._merged_entry

    def post_action(self) -> str:
        return self.post_action_combo.currentData()

    def source_entry_ids(self) -> list[str]:
        return getattr(self, "_source_ids", [])
