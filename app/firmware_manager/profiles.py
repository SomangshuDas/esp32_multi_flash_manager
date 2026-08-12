"""
profiles.py
============
Firmware Profiles let manufacturing operators pick a named preset
(e.g. "ESP32 RFID Reader") and instantly load the correct firmware list
and flash settings onto a device, instead of configuring everything by
hand every time. Profiles are stored as JSON files in the user's app-data
directory under profiles/*.json so they persist across projects and can
be shared between operators by copying files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import (
    DEFAULT_BAUD, DEFAULT_CHIP, DEFAULT_FLASH_FREQ,
    DEFAULT_FLASH_MODE, DEFAULT_FLASH_SIZE,
)
from app.utilities.helpers import get_app_data_dir, safe_filename

logger = get_logger(__name__)


@dataclass
class FirmwareProfile:
    """A reusable, named bundle of firmware files + flash settings."""

    name: str
    chip_type: str = DEFAULT_CHIP
    baud_rate: int = DEFAULT_BAUD
    flash_mode: str = DEFAULT_FLASH_MODE
    flash_frequency: str = DEFAULT_FLASH_FREQ
    flash_size: str = DEFAULT_FLASH_SIZE
    erase_before_upload: bool = False
    firmware: list[FirmwareEntry] = field(default_factory=list)

    def apply_to_device(self, device: DeviceConfig) -> None:
        """Overwrite the given device's settings + firmware with this profile."""
        device.chip_type = self.chip_type
        device.baud_rate = self.baud_rate
        device.flash_mode = self.flash_mode
        device.flash_frequency = self.flash_frequency
        device.flash_size = self.flash_size
        device.erase_before_upload = self.erase_before_upload
        device.firmware = [f.duplicate() for f in self.firmware]
        for entry in device.firmware:
            entry.refresh()

    @staticmethod
    def from_device(name: str, device: DeviceConfig) -> "FirmwareProfile":
        """Create a new profile by capturing an existing device's config."""
        return FirmwareProfile(
            name=name,
            chip_type=device.chip_type,
            baud_rate=device.baud_rate,
            flash_mode=device.flash_mode,
            flash_frequency=device.flash_frequency,
            flash_size=device.flash_size,
            erase_before_upload=device.erase_before_upload,
            firmware=[f.duplicate() for f in device.firmware],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "chip_type": self.chip_type,
            "baud_rate": self.baud_rate,
            "flash_mode": self.flash_mode,
            "flash_frequency": self.flash_frequency,
            "flash_size": self.flash_size,
            "erase_before_upload": self.erase_before_upload,
            "firmware": [f.to_dict() for f in self.firmware],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FirmwareProfile":
        return FirmwareProfile(
            name=data.get("name", "Unnamed Profile"),
            chip_type=data.get("chip_type", DEFAULT_CHIP),
            baud_rate=data.get("baud_rate", DEFAULT_BAUD),
            flash_mode=data.get("flash_mode", DEFAULT_FLASH_MODE),
            flash_frequency=data.get("flash_frequency", DEFAULT_FLASH_FREQ),
            flash_size=data.get("flash_size", DEFAULT_FLASH_SIZE),
            erase_before_upload=data.get("erase_before_upload", False),
            firmware=[FirmwareEntry.from_dict(f) for f in data.get("firmware", [])],
        )


def _profiles_dir() -> Path:
    directory = get_app_data_dir() / "profiles"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_profiles() -> list[FirmwareProfile]:
    """Load every profile JSON file from the profiles directory."""
    profiles: list[FirmwareProfile] = []
    for file in sorted(_profiles_dir().glob("*.json")):
        try:
            with file.open("r", encoding="utf-8") as handle:
                profiles.append(FirmwareProfile.from_dict(json.load(handle)))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load firmware profile: %s", file)
    return profiles


def save_profile(profile: FirmwareProfile) -> None:
    file_path = _profiles_dir() / f"{safe_filename(profile.name)}.json"
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(profile.to_dict(), handle, indent=2, ensure_ascii=False)
    logger.info("Saved firmware profile '%s' to %s", profile.name, file_path)


def delete_profile(name: str) -> None:
    file_path = _profiles_dir() / f"{safe_filename(name)}.json"
    if file_path.exists():
        file_path.unlink()
        logger.info("Deleted firmware profile '%s'", name)
