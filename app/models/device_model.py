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
    DEFAULT_FLASH_FREQ,
    DEFAULT_FLASH_MODE,
    DEFAULT_FLASH_SIZE,
    STATUS_WAITING,
)
from app.utilities.helpers import new_uuid


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
    verify_flash: bool = True
    reset_after_upload: bool = True
    compression: bool = True
    stub_loader: bool = True
    custom_flash_args: str = ""
    firmware: list[FirmwareEntry] = field(default_factory=list)

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
            verify_flash=self.verify_flash,
            reset_after_upload=self.reset_after_upload,
            compression=self.compression,
            stub_loader=self.stub_loader,
            custom_flash_args=self.custom_flash_args,
            firmware=[f.duplicate() for f in self.firmware],
        )
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
            "verify_flash": self.verify_flash,
            "reset_after_upload": self.reset_after_upload,
            "compression": self.compression,
            "stub_loader": self.stub_loader,
            "custom_flash_args": self.custom_flash_args,
            "firmware": [f.to_dict() for f in self.firmware],
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
            verify_flash=data.get("verify_flash", True),
            reset_after_upload=data.get("reset_after_upload", True),
            compression=data.get("compression", True),
            stub_loader=data.get("stub_loader", True),
            custom_flash_args=data.get("custom_flash_args", ""),
            firmware=[FirmwareEntry.from_dict(f) for f in data.get("firmware", [])],
        )
        return device
