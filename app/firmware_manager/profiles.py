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
import os
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


def _atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    """Write `data` as JSON to `file_path` atomically (temp file +
    os.replace), so a crash/power-loss mid-write can never leave a
    truncated/corrupt profile file behind."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_name(f".{file_path.name}.tmp-{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, file_path)


def save_profile(profile: FirmwareProfile) -> None:
    file_path = _profiles_dir() / f"{safe_filename(profile.name)}.json"
    _atomic_write_json(file_path, profile.to_dict())
    logger.info("Saved firmware profile '%s' to %s", profile.name, file_path)


def delete_profile(name: str) -> None:
    file_path = _profiles_dir() / f"{safe_filename(name)}.json"
    if file_path.exists():
        file_path.unlink()
        logger.info("Deleted firmware profile '%s'", name)


def export_profile_to_file(profile: FirmwareProfile, dest_path: str | Path) -> None:
    """
    Save `profile` to an arbitrary user-chosen path (e.g. a USB drive or
    shared network folder) instead of the app-data profiles directory.

    Previously the only way to share a profile between operators/benches
    was to manually locate and copy the underlying file out of the
    per-user app-data profiles folder -- this is the explicit "Export..."
    counterpart wired into ProfileDialog (see app/ui/profile_dialog.py).
    """
    dest_path = Path(dest_path)
    _atomic_write_json(dest_path, profile.to_dict())
    logger.info("Exported firmware profile '%s' to %s", profile.name, dest_path)


def import_profile_from_file(src_path: str | Path) -> FirmwareProfile:
    """
    Load a FirmwareProfile from an arbitrary file (as written by
    export_profile_to_file, on this machine or another one) WITHOUT
    installing it into the app-data profiles directory -- the caller
    (ProfileDialog) decides whether/how to save it after previewing it,
    mirroring the "Import..." counterpart to export_profile_to_file
    above.

    Raises the same exceptions list_profiles() would silently log and
    skip (OSError, json.JSONDecodeError) -- unlike loading the profiles
    directory's own files at startup, a failure here is a single
    explicit user action and should surface as a clear error dialog
    rather than being swallowed.
    """
    with Path(src_path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{src_path} does not contain a valid firmware profile.")
    return FirmwareProfile.from_dict(data)
