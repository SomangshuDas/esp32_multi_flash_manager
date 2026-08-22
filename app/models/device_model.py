"""
device_model.py
================
Data model describing a single ESP32 device configuration: its serial
connection parameters, flashing options, its firmware list, and its
current runtime status. This is a plain Python object (not a QObject) so
it stays trivially serializable; runtime signalling is handled separately
by DeviceController via Qt signals keyed off device id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import (
    DEFAULT_BAUD,
    DEFAULT_CHIP,
    DEFAULT_FLASH_ENCRYPTION_MODE,
    DEFAULT_FLASH_FREQ,
    DEFAULT_FLASH_MODE,
    DEFAULT_FLASH_SIZE,
    DEFAULT_KEY_SOURCE,
    DEFAULT_SECURE_BOOT_SCHEME,
    DEFAULT_SECURE_BOOT_VERSION,
    DEFAULT_UNIFIED_KEY_BLOCK,
    STATUS_WAITING,
)
from app.utilities.helpers import new_uuid


@dataclass
class SecurityConfig:
    """
    Per-device flash-encryption / secure-boot provisioning settings.

    Nothing here performs cryptography itself -- it only records what the
    user wants so app/flash_engine/security_manager.py can build the
    equivalent `espsecure`/`espefuse` command lines. See that module's
    docstring for the full command mapping.
    """

    # --- Flash encryption ---
    enable_flash_encryption: bool = False
    flash_encryption_mode: str = DEFAULT_FLASH_ENCRYPTION_MODE  # "development" | "release"

    # --- Secure boot ---
    enable_secure_boot: bool = False
    secure_boot_version: str = DEFAULT_SECURE_BOOT_VERSION  # "1" | "2"
    secure_boot_scheme: str = DEFAULT_SECURE_BOOT_SCHEME  # rsa3072/ecdsa192/ecdsa256/ecdsa384 (v2 only)

    # --- Key sourcing (shared by both features; each burns its own block) ---
    key_source: str = DEFAULT_KEY_SOURCE  # "generate" | "existing"
    flash_encryption_key_path: str = ""
    secure_boot_key_path: str = ""

    # --- eFuse block/purpose targeting (unified-eFuse-table chips only;
    #     ignored for legacy ESP32, which uses fixed block names) ---
    flash_encryption_key_block: str = DEFAULT_UNIFIED_KEY_BLOCK
    secure_boot_key_block: str = "BLOCK_KEY1"

    # --- Safety knobs ---
    keep_key_readable: bool = False  # maps to espefuse's --no-protect-key / --no-read-protect
    encrypt_on_write: bool = True  # append esptool write-flash's --encrypt (dev-mode on-the-fly encryption)

    # Power-user passthrough for espefuse invocations, mirroring
    # DeviceConfig.custom_flash_args' existing pattern.
    custom_efuse_args: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable_flash_encryption": self.enable_flash_encryption,
            "flash_encryption_mode": self.flash_encryption_mode,
            "enable_secure_boot": self.enable_secure_boot,
            "secure_boot_version": self.secure_boot_version,
            "secure_boot_scheme": self.secure_boot_scheme,
            "key_source": self.key_source,
            "flash_encryption_key_path": self.flash_encryption_key_path,
            "secure_boot_key_path": self.secure_boot_key_path,
            "flash_encryption_key_block": self.flash_encryption_key_block,
            "secure_boot_key_block": self.secure_boot_key_block,
            "keep_key_readable": self.keep_key_readable,
            "encrypt_on_write": self.encrypt_on_write,
            "custom_efuse_args": self.custom_efuse_args,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SecurityConfig":
        return SecurityConfig(
            enable_flash_encryption=data.get("enable_flash_encryption", False),
            flash_encryption_mode=data.get("flash_encryption_mode", DEFAULT_FLASH_ENCRYPTION_MODE),
            enable_secure_boot=data.get("enable_secure_boot", False),
            secure_boot_version=data.get("secure_boot_version", DEFAULT_SECURE_BOOT_VERSION),
            secure_boot_scheme=data.get("secure_boot_scheme", DEFAULT_SECURE_BOOT_SCHEME),
            key_source=data.get("key_source", DEFAULT_KEY_SOURCE),
            flash_encryption_key_path=data.get("flash_encryption_key_path", ""),
            secure_boot_key_path=data.get("secure_boot_key_path", ""),
            flash_encryption_key_block=data.get("flash_encryption_key_block", DEFAULT_UNIFIED_KEY_BLOCK),
            secure_boot_key_block=data.get("secure_boot_key_block", "BLOCK_KEY1"),
            keep_key_readable=data.get("keep_key_readable", False),
            encrypt_on_write=data.get("encrypt_on_write", True),
            custom_efuse_args=data.get("custom_efuse_args", ""),
        )

    def clone(self) -> "SecurityConfig":
        return SecurityConfig.from_dict(self.to_dict())


@dataclass
class DeviceRuntimeState:
    """Transient, non-persisted runtime/progress information for a device."""

    status: str = STATUS_WAITING
    progress_percent: int = 0
    current_file: str = ""
    current_address: str = ""
    transfer_speed_kbps: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    error_message: str = ""
    connected: bool = False
    log_lines: list[str] = field(default_factory=list)

    # Populated by a "Read Flash / eFuse / Chip Info" -> Security Info read
    # (see app/workers/read_worker.py); None means "unknown / never read",
    # not "confirmed disabled". Used by the pre-upload validator to catch
    # the foot-gun of flashing unencrypted firmware to a device that was
    # already provisioned with flash encryption.
    flash_encryption_detected: bool | None = None
    secure_boot_detected: bool | None = None


@dataclass
class DeviceConfig:
    """Persisted configuration for one ESP32 device / flashing target."""

    id: str = field(default_factory=new_uuid)
    name: str = "New Device"
    com_port: str = ""
    chip_type: str = DEFAULT_CHIP
    baud_rate: int = DEFAULT_BAUD
    flash_mode: str = DEFAULT_FLASH_MODE
    flash_frequency: str = DEFAULT_FLASH_FREQ
    flash_size: str = DEFAULT_FLASH_SIZE
    erase_before_upload: bool = False
    reset_after_upload: bool = True
    compression: bool = True
    stub_loader: bool = True
    custom_flash_args: str = ""
    firmware: list[FirmwareEntry] = field(default_factory=list)

    # Flash encryption / secure boot provisioning settings for this device
    # (see SecurityConfig above and app/flash_engine/security_manager.py).
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Runtime state is kept on the model for convenience but is excluded
    # from persistence (see to_dict).
    runtime: DeviceRuntimeState = field(default_factory=DeviceRuntimeState)

    # ------------------------------------------------------------------
    # Firmware list operations
    # ------------------------------------------------------------------
    def add_firmware(self, entry: FirmwareEntry) -> None:
        self.firmware.append(entry)

    def remove_firmware(self, firmware_id: str) -> None:
        self.firmware = [f for f in self.firmware if f.id != firmware_id]

    def move_firmware(self, firmware_id: str, direction: int) -> None:
        """direction: -1 to move up, +1 to move down."""
        index = next((i for i, f in enumerate(self.firmware) if f.id == firmware_id), None)
        if index is None:
            return
        new_index = index + direction
        if 0 <= new_index < len(self.firmware):
            self.firmware[index], self.firmware[new_index] = (
                self.firmware[new_index],
                self.firmware[index],
            )

    def duplicate_firmware(self, firmware_id: str) -> None:
        for i, entry in enumerate(self.firmware):
            if entry.id == firmware_id:
                self.firmware.insert(i + 1, entry.duplicate())
                return

    def enabled_firmware(self) -> list[FirmwareEntry]:
        return [f for f in self.firmware if f.enabled]

    # ------------------------------------------------------------------
    # Cloning / templating
    # ------------------------------------------------------------------
    def clone(self, new_name: str | None = None) -> "DeviceConfig":
        """Deep-clone this device (used by 'Duplicate Device' / templates)."""
        clone = DeviceConfig(
            id=new_uuid(),
            name=new_name or f"{self.name} (Copy)",
            com_port="",  # a clone must not steal the original's port
            chip_type=self.chip_type,
            baud_rate=self.baud_rate,
            flash_mode=self.flash_mode,
            flash_frequency=self.flash_frequency,
            flash_size=self.flash_size,
            erase_before_upload=self.erase_before_upload,
            reset_after_upload=self.reset_after_upload,
            compression=self.compression,
            stub_loader=self.stub_loader,
            custom_flash_args=self.custom_flash_args,
            firmware=[f.duplicate() for f in self.firmware],
        )
        # Security settings are cloned too (a duplicated device is meant to
        # be an exact template of the original) but the key SOURCE FILES
        # themselves are simply referenced, not copied on disk -- if the
        # original used a generated per-device key, the clone should
        # generate its own rather than silently sharing key material.
        clone.security = self.security.clone()
        if self.security.key_source == "generate":
            clone.security.flash_encryption_key_path = ""
            clone.security.secure_boot_key_path = ""
        return clone

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "com_port": self.com_port,
            "chip_type": self.chip_type,
            "baud_rate": self.baud_rate,
            "flash_mode": self.flash_mode,
            "flash_frequency": self.flash_frequency,
            "flash_size": self.flash_size,
            "erase_before_upload": self.erase_before_upload,
            "reset_after_upload": self.reset_after_upload,
            "compression": self.compression,
            "stub_loader": self.stub_loader,
            "custom_flash_args": self.custom_flash_args,
            "firmware": [f.to_dict() for f in self.firmware],
            "security": self.security.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DeviceConfig":
        device = DeviceConfig(
            id=data.get("id", new_uuid()),
            name=data.get("name", "Device"),
            com_port=data.get("com_port", ""),
            chip_type=data.get("chip_type", DEFAULT_CHIP),
            baud_rate=data.get("baud_rate", DEFAULT_BAUD),
            flash_mode=data.get("flash_mode", DEFAULT_FLASH_MODE),
            flash_frequency=data.get("flash_frequency", DEFAULT_FLASH_FREQ),
            flash_size=data.get("flash_size", DEFAULT_FLASH_SIZE),
            erase_before_upload=data.get("erase_before_upload", False),
            reset_after_upload=data.get("reset_after_upload", True),
            compression=data.get("compression", True),
            stub_loader=data.get("stub_loader", True),
            custom_flash_args=data.get("custom_flash_args", ""),
            firmware=[FirmwareEntry.from_dict(f) for f in data.get("firmware", [])],
        )
        device.security = SecurityConfig.from_dict(data.get("security", {}))
        return device
