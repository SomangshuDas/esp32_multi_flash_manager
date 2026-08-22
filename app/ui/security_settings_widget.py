"""
security_settings_widget.py
=============================
"Security" tab in the device settings area: per-device flash encryption /
secure boot configuration, built entirely on top of `espsecure`/`espefuse`
(see app/flash_engine/security_manager.py -- nothing here implements any
cryptography itself). Mirrors DeviceSettingsWidget's commit-on-change
pattern so it plugs into the same locking (mid-flash / Settings Lock)
behaviour MainWindow already applies to the Firmware/Device Settings tabs.

The irreversibility warning required by the spec is surfaced right here in
the tab itself (not just in documentation) via a permanent, always-visible
banner, and again -- unskippably -- in ProvisionConfirmDialog before any
eFuse write actually runs (see provision_dialog.py).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.flash_engine.security_manager import is_legacy_efuse_chip, validate_security_settings
from app.models.device_model import DeviceConfig
from app.ui.widgets import make_scrollable
from app.utilities.constants import (
    DEFAULT_UNIFIED_KEY_BLOCK,
    FLASH_ENCRYPTION_MODE_LABELS,
    FLASH_ENCRYPTION_MODES,
    KEY_SOURCE_LABELS,
    KEY_SOURCE_OPTIONS,
    SECURE_BOOT_SCHEMES,
    SECURE_BOOT_VERSIONS,
)
from app.utilities.helpers import safe_filename


class SecuritySettingsWidget(QWidget):
    """
    Signals
    -------
    settings_changed(device_id)         - fires after any field edit is committed
    provision_requested(device_id)       - "Provision Device (Burn eFuses)..." clicked
    """

    settings_changed = Signal(str)
    provision_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._device: DeviceConfig | None = None
        self._loading = False
        self._locked = False
        self._factory_locked = False

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        layout = QVBoxLayout(content)

        self.title_label = QLabel("Security — (no device selected)")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(self.title_label)

        banner = QLabel(
            "&#9888; Burning eFuses (flash encryption / secure boot keys) is "
            "<b>permanent and irreversible</b> on real hardware. Nothing is burned "
            "until you explicitly confirm on the Provision dialog."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            "color: #e03131; background-color: rgba(224,49,49,0.08); "
            "border: 1px solid #e03131; border-radius: 4px; padding: 6px;"
        )
        layout.addWidget(banner)

        # ---------------- Flash Encryption ----------------
        fe_group = QGroupBox("Flash Encryption")
        fe_form = QFormLayout(fe_group)
        self.fe_enable_check = QCheckBox("Enable flash encryption for this device")
        fe_form.addRow(self.fe_enable_check)

        self.fe_mode_combo = QComboBox()
        for value in FLASH_ENCRYPTION_MODES:
            self.fe_mode_combo.addItem(FLASH_ENCRYPTION_MODE_LABELS[value], value)
        fe_form.addRow("Mode:", self.fe_mode_combo)

        self.fe_key_source_combo = QComboBox()
        for value in KEY_SOURCE_OPTIONS:
            self.fe_key_source_combo.addItem(KEY_SOURCE_LABELS[value], value)
        fe_form.addRow("Key:", self.fe_key_source_combo)

        fe_key_row = QHBoxLayout()
        self.fe_key_path_edit = QLineEdit()
        self.fe_key_path_edit.setPlaceholderText("Path to 32/64-byte AES key file")
        fe_key_browse = QPushButton("Browse...")
        fe_key_browse.clicked.connect(self._browse_fe_key)
        fe_key_row.addWidget(self.fe_key_path_edit, 1)
        fe_key_row.addWidget(fe_key_browse)
        fe_form.addRow("Key File:", fe_key_row)

        self.fe_key_block_edit = QLineEdit(DEFAULT_UNIFIED_KEY_BLOCK)
        self.fe_key_block_edit.setToolTip(
            "eFuse key block to burn the flash-encryption key into (e.g. BLOCK_KEY0). "
            "Ignored on the original ESP32, which uses a fixed block name."
        )
        fe_form.addRow("eFuse Key Block:", self.fe_key_block_edit)

        self.fe_encrypt_on_write_check = QCheckBox("Pass --encrypt on every Upload (on-the-fly write encryption)")
        fe_form.addRow(self.fe_encrypt_on_write_check)

        layout.addWidget(fe_group)

        # ---------------- Secure Boot ----------------
        sb_group = QGroupBox("Secure Boot")
        sb_form = QFormLayout(sb_group)
        self.sb_enable_check = QCheckBox("Enable secure boot for this device")
        sb_form.addRow(self.sb_enable_check)

        self.sb_version_combo = QComboBox()
        self.sb_version_combo.addItems(SECURE_BOOT_VERSIONS)
        sb_form.addRow("Version:", self.sb_version_combo)

        self.sb_scheme_combo = QComboBox()
        self.sb_scheme_combo.addItems(SECURE_BOOT_SCHEMES)
        sb_form.addRow("Signing Scheme (V2 only):", self.sb_scheme_combo)

        self.sb_key_source_combo = QComboBox()
        for value in KEY_SOURCE_OPTIONS:
            self.sb_key_source_combo.addItem(KEY_SOURCE_LABELS[value], value)
        sb_form.addRow("Key:", self.sb_key_source_combo)

        sb_key_row = QHBoxLayout()
        self.sb_key_path_edit = QLineEdit()
        self.sb_key_path_edit.setPlaceholderText("Path to a PEM signing key")
        sb_key_browse = QPushButton("Browse...")
        sb_key_browse.clicked.connect(self._browse_sb_key)
        sb_key_row.addWidget(self.sb_key_path_edit, 1)
        sb_key_row.addWidget(sb_key_browse)
        sb_form.addRow("Key File:", sb_key_row)

        self.sb_key_block_edit = QLineEdit("BLOCK_KEY1")
        self.sb_key_block_edit.setToolTip(
            "eFuse key block to burn the secure-boot key digest into (e.g. BLOCK_KEY1). "
            "Ignored on the original ESP32, which uses a fixed block name."
        )
        sb_form.addRow("eFuse Key Block:", self.sb_key_block_edit)

        layout.addWidget(sb_group)

        # ---------------- Advanced / power-user ----------------
        adv_group = QGroupBox("Advanced")
        adv_form = QFormLayout(adv_group)
        self.keep_readable_check = QCheckBox(
            "Leave burned key readable/writable (NOT recommended -- disables espefuse's own key protection)"
        )
        adv_form.addRow(self.keep_readable_check)
        self.custom_efuse_args_edit = QLineEdit()
        self.custom_efuse_args_edit.setPlaceholderText("e.g. --force-write-always")
        adv_form.addRow("Custom eFuse Arguments:", self.custom_efuse_args_edit)
        layout.addWidget(adv_group)

        # ---------------- Provision action ----------------
        action_row = QHBoxLayout()
        self.provision_button = QPushButton("Provision Device (Burn eFuses)...")
        self.provision_button.setObjectName("primaryButton")
        self.provision_button.clicked.connect(self._on_provision_clicked)
        self.validate_button = QPushButton("Validate Settings")
        self.validate_button.clicked.connect(self._on_validate_clicked)
        action_row.addWidget(self.validate_button)
        action_row.addWidget(self.provision_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch(1)
        outer_layout.addWidget(make_scrollable(content))

        self._wire_commit_signals()
        self.set_device(None)

    # ------------------------------------------------------------------
    def _wire_commit_signals(self) -> None:
        self.fe_enable_check.toggled.connect(self._commit)
        self.fe_mode_combo.currentIndexChanged.connect(self._commit)
        self.fe_key_source_combo.currentIndexChanged.connect(self._commit)
        self.fe_key_path_edit.editingFinished.connect(self._commit)
        self.fe_key_block_edit.editingFinished.connect(self._commit)
        self.fe_encrypt_on_write_check.toggled.connect(self._commit)
        self.sb_enable_check.toggled.connect(self._commit)
        self.sb_version_combo.currentIndexChanged.connect(self._commit)
        self.sb_scheme_combo.currentIndexChanged.connect(self._commit)
        self.sb_key_source_combo.currentIndexChanged.connect(self._commit)
        self.sb_key_path_edit.editingFinished.connect(self._commit)
        self.sb_key_block_edit.editingFinished.connect(self._commit)
        self.keep_readable_check.toggled.connect(self._commit)
        self.custom_efuse_args_edit.editingFinished.connect(self._commit)

    # ------------------------------------------------------------------
    def _browse_fe_key(self) -> None:
        default_name = f"{safe_filename(self._device.name) if self._device else 'device'}_flash_encryption.key"
        path, _ = QFileDialog.getSaveFileName(
            self, "Flash Encryption Key File", self.fe_key_path_edit.text() or default_name,
            "Key Files (*.bin *.key);;All Files (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self.fe_key_path_edit.setText(path)
            self._commit()

    def _browse_sb_key(self) -> None:
        default_name = f"{safe_filename(self._device.name) if self._device else 'device'}_secure_boot_signing.pem"
        path, _ = QFileDialog.getSaveFileName(
            self, "Secure Boot Signing Key File", self.sb_key_path_edit.text() or default_name,
            "Key Files (*.pem);;All Files (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self.sb_key_path_edit.setText(path)
            self._commit()

    # ------------------------------------------------------------------
    def set_device(self, device: DeviceConfig | None, locked: bool = False) -> None:
        self._device = device
        self._locked = locked
        self._loading = True
        enabled = device is not None and not locked and not self._factory_locked
        title = f"Security — {device.name}" if device else "Security — (no device selected)"
        if device is not None and locked:
            title += "  (locked — flashing in progress)"
        elif device is not None and self._factory_locked:
            title += "  (locked — Settings Lock)"
        self.title_label.setText(title)

        sec = device.security if device is not None else DeviceConfig().security

        self.fe_enable_check.setChecked(sec.enable_flash_encryption)
        self.fe_mode_combo.setCurrentIndex(max(0, self.fe_mode_combo.findData(sec.flash_encryption_mode)))
        self.fe_key_source_combo.setCurrentIndex(max(0, self.fe_key_source_combo.findData(sec.key_source)))
        self.fe_key_path_edit.setText(sec.flash_encryption_key_path)
        self.fe_key_block_edit.setText(sec.flash_encryption_key_block)
        self.fe_encrypt_on_write_check.setChecked(sec.encrypt_on_write)

        self.sb_enable_check.setChecked(sec.enable_secure_boot)
        self.sb_version_combo.setCurrentText(sec.secure_boot_version)
        self.sb_scheme_combo.setCurrentText(sec.secure_boot_scheme)
        self.sb_key_source_combo.setCurrentIndex(max(0, self.sb_key_source_combo.findData(sec.key_source)))
        self.sb_key_path_edit.setText(sec.secure_boot_key_path)
        self.sb_key_block_edit.setText(sec.secure_boot_key_block)

        self.keep_readable_check.setChecked(sec.keep_key_readable)
        self.custom_efuse_args_edit.setText(sec.custom_efuse_args)

        legacy = device is not None and is_legacy_efuse_chip(device.chip_type)
        self.fe_key_block_edit.setEnabled(enabled and not legacy)
        self.sb_key_block_edit.setEnabled(enabled and not legacy)

        for widget in (
            self.fe_enable_check, self.fe_mode_combo, self.fe_key_source_combo,
            self.fe_key_path_edit, self.fe_encrypt_on_write_check,
            self.sb_enable_check, self.sb_version_combo, self.sb_scheme_combo,
            self.sb_key_source_combo, self.sb_key_path_edit,
            self.keep_readable_check, self.custom_efuse_args_edit,
            self.validate_button,
        ):
            widget.setEnabled(enabled)
        self.provision_button.setEnabled(
            enabled and (sec.enable_flash_encryption or sec.enable_secure_boot)
        )

        self.status_label.setText("")
        self._loading = False

    def current_device_id(self) -> str | None:
        return self._device.id if self._device is not None else None

    def refresh_display(self) -> None:
        if self._device is not None:
            self.set_device(self._device, locked=self._locked)

    def set_locked(self, locked: bool) -> None:
        if self._device is not None and locked != self._locked:
            self.set_device(self._device, locked=locked)

    def set_factory_locked(self, locked: bool) -> None:
        self._factory_locked = locked
        self.refresh_display()

    # ------------------------------------------------------------------
    def _commit(self, *_args) -> None:
        if self._loading or self._device is None or self._locked or self._factory_locked:
            return
        sec = self._device.security
        sec.enable_flash_encryption = self.fe_enable_check.isChecked()
        sec.flash_encryption_mode = self.fe_mode_combo.currentData() or sec.flash_encryption_mode
        sec.key_source = self.fe_key_source_combo.currentData() or sec.key_source
        sec.flash_encryption_key_path = self.fe_key_path_edit.text().strip()
        sec.flash_encryption_key_block = self.fe_key_block_edit.text().strip() or DEFAULT_UNIFIED_KEY_BLOCK
        sec.encrypt_on_write = self.fe_encrypt_on_write_check.isChecked()

        sec.enable_secure_boot = self.sb_enable_check.isChecked()
        sec.secure_boot_version = self.sb_version_combo.currentText()
        sec.secure_boot_scheme = self.sb_scheme_combo.currentText()
        # Secure boot's key source combo shares the same underlying field as
        # flash encryption's (one "how do I get a key" choice per device);
        # whichever combo the user touched last wins.
        sec.key_source = self.sb_key_source_combo.currentData() or sec.key_source
        sec.secure_boot_key_path = self.sb_key_path_edit.text().strip()
        sec.secure_boot_key_block = self.sb_key_block_edit.text().strip() or "BLOCK_KEY1"

        sec.keep_key_readable = self.keep_readable_check.isChecked()
        sec.custom_efuse_args = self.custom_efuse_args_edit.text()

        self.provision_button.setEnabled(
            not self._locked and not self._factory_locked
            and (sec.enable_flash_encryption or sec.enable_secure_boot)
        )
        self.settings_changed.emit(self._device.id)

    # ------------------------------------------------------------------
    def _on_validate_clicked(self) -> None:
        if self._device is None:
            return
        report = validate_security_settings(self._device)
        if not report.issues:
            self.status_label.setStyleSheet("color: #2f9e44;")
            self.status_label.setText("No issues found.")
            return
        lines = []
        for issue in report.issues:
            color = "#e03131" if issue.is_error else "#e0a300"
            label = "Error" if issue.is_error else "Warning"
            lines.append(f"<span style='color:{color};'>[{label}]</span> {issue.message}")
        self.status_label.setStyleSheet("")
        self.status_label.setText("<br>".join(lines))

    def _on_provision_clicked(self) -> None:
        if self._device is not None:
            self.provision_requested.emit(self._device.id)
