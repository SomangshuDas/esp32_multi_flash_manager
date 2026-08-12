"""
device_settings_widget.py
==========================
Form panel for editing all per-device settings: name, serial port, chip,
baud rate, flash mode/frequency/size, and the boolean flashing options
(erase / reset / compression / stub loader), plus a free-text
custom-arguments field for power users.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.device_manager.port_scanner import list_available_ports
from app.models.device_model import DeviceConfig
from app.utilities.constants import (
    BAUD_RATES, FLASH_FREQUENCIES, FLASH_MODES, FLASH_SIZES, SUPPORTED_CHIPS,
)


class DeviceSettingsWidget(QWidget):
    """Signal settings_changed(device_id) fires after any field edit is committed."""

    settings_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._device: DeviceConfig | None = None
        self._loading = False

        layout = QVBoxLayout(self)
        self.title_label = QLabel("Settings — (no device selected)")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(self.title_label)

        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.refresh_ports_button_hint = QLabel("(ports refresh automatically)")
        self.chip_combo = QComboBox()
        self.chip_combo.addItems(SUPPORTED_CHIPS)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([str(b) for b in BAUD_RATES])
        self.baud_combo.setEditable(True)
        self.flash_mode_combo = QComboBox()
        self.flash_mode_combo.addItems(FLASH_MODES)
        self.flash_freq_combo = QComboBox()
        self.flash_freq_combo.addItems(FLASH_FREQUENCIES)
        self.flash_size_combo = QComboBox()
        self.flash_size_combo.addItems(FLASH_SIZES)

        self.erase_check = QCheckBox("Erase flash before upload")
        self.reset_check = QCheckBox("Reset device after upload")
        self.compression_check = QCheckBox("Enable compression")
        self.stub_check = QCheckBox("Use stub loader (recommended)")

        self.custom_args_edit = QLineEdit()
        self.custom_args_edit.setPlaceholderText("e.g. --no-progress --connect-attempts 5")

        form.addRow("Friendly Name:", self.name_edit)
        form.addRow("Port:", self.port_combo)
        form.addRow("Chip Type:", self.chip_combo)
        form.addRow("Upload Speed (baud):", self.baud_combo)
        form.addRow("Flash Mode:", self.flash_mode_combo)
        form.addRow("Flash Frequency:", self.flash_freq_combo)
        form.addRow("Flash Size:", self.flash_size_combo)
        form.addRow(self.erase_check)
        form.addRow(self.reset_check)
        form.addRow(self.compression_check)
        form.addRow(self.stub_check)
        form.addRow("Custom Flash Arguments:", self.custom_args_edit)

        layout.addLayout(form)
        layout.addStretch(1)

        self.refresh_available_ports()

        # Wire change signals AFTER initial population to avoid spurious commits.
        self.name_edit.editingFinished.connect(self._commit)
        self.port_combo.currentTextChanged.connect(self._commit)
        self.chip_combo.currentTextChanged.connect(self._commit)
        self.baud_combo.currentTextChanged.connect(self._commit)
        self.flash_mode_combo.currentTextChanged.connect(self._commit)
        self.flash_freq_combo.currentTextChanged.connect(self._commit)
        self.flash_size_combo.currentTextChanged.connect(self._commit)
        self.erase_check.toggled.connect(self._commit)
        self.reset_check.toggled.connect(self._commit)
        self.compression_check.toggled.connect(self._commit)
        self.stub_check.toggled.connect(self._commit)
        self.custom_args_edit.editingFinished.connect(self._commit)

        self.set_device(None)

    # ------------------------------------------------------------------
    def refresh_available_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItems([p.device for p in list_available_ports()])
        if current:
            self.port_combo.setEditText(current)
        self.port_combo.blockSignals(False)

    # ------------------------------------------------------------------
    def set_device(self, device: DeviceConfig | None) -> None:
        self._device = device
        self._loading = True
        enabled = device is not None
        self.title_label.setText(f"Settings — {device.name}" if device else "Settings — (no device selected)")

        if device:
            self.name_edit.setText(device.name)
            self.port_combo.setEditText(device.com_port)
            self.chip_combo.setCurrentText(device.chip_type)
            self.baud_combo.setCurrentText(str(device.baud_rate))
            self.flash_mode_combo.setCurrentText(device.flash_mode)
            self.flash_freq_combo.setCurrentText(device.flash_frequency)
            self.flash_size_combo.setCurrentText(device.flash_size)
            self.erase_check.setChecked(device.erase_before_upload)
            self.reset_check.setChecked(device.reset_after_upload)
            self.compression_check.setChecked(device.compression)
            self.stub_check.setChecked(device.stub_loader)
            self.custom_args_edit.setText(device.custom_flash_args)
        else:
            self.name_edit.clear()
            self.port_combo.setEditText("")
            self.custom_args_edit.clear()

        for widget in (
            self.name_edit, self.port_combo, self.chip_combo, self.baud_combo,
            self.flash_mode_combo, self.flash_freq_combo, self.flash_size_combo,
            self.erase_check, self.reset_check,
            self.compression_check, self.stub_check, self.custom_args_edit,
        ):
            widget.setEnabled(enabled)

        self._loading = False

    # ------------------------------------------------------------------
    def _commit(self, *_args) -> None:
        if self._loading or self._device is None:
            return
        device = self._device
        device.name = self.name_edit.text().strip() or device.name
        device.com_port = self.port_combo.currentText().strip()
        device.chip_type = self.chip_combo.currentText()
        try:
            device.baud_rate = int(self.baud_combo.currentText())
        except ValueError:
            pass
        device.flash_mode = self.flash_mode_combo.currentText()
        device.flash_frequency = self.flash_freq_combo.currentText()
        device.flash_size = self.flash_size_combo.currentText()
        device.erase_before_upload = self.erase_check.isChecked()
        device.reset_after_upload = self.reset_check.isChecked()
        device.compression = self.compression_check.isChecked()
        device.stub_loader = self.stub_check.isChecked()
        device.custom_flash_args = self.custom_args_edit.text()
        self.settings_changed.emit(device.id)
