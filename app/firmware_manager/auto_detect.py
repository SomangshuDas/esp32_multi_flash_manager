"""
auto_detect.py
===============
Scans a firmware folder and builds a list of FirmwareEntry objects,
automatically assigning well-known addresses to recognized filenames
(bootloader.bin, partition-table.bin, firmware.bin, ...) while leaving
unknown .bin files present but with an editable placeholder address so
the user can assign one manually.
"""

from __future__ import annotations

from pathlib import Path

from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import KNOWN_FIRMWARE_ADDRESSES

logger = get_logger(__name__)

# Fallback address offered to unrecognized .bin files so the field is never
# blank; the user is expected to edit it before flashing (validator will
# flag duplicate/blank addresses).
UNKNOWN_BIN_PLACEHOLDER_ADDRESS = "0x0"


def scan_firmware_folder(folder_path: str) -> list[FirmwareEntry]:
    """
    Scan `folder_path` (non-recursive) for .bin files and return a list of
    FirmwareEntry objects with addresses pre-assigned for recognized names.
    Recognized files are ordered by their flash address; unknown files are
    appended afterwards in alphabetical order.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        logger.warning("scan_firmware_folder called on non-directory: %s", folder_path)
        return []

    bin_files = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".bin"],
        key=lambda f: f.name.lower(),
    )

    known: list[FirmwareEntry] = []
    unknown: list[FirmwareEntry] = []

    for bin_file in bin_files:
        lower_name = bin_file.name.lower()
        address = KNOWN_FIRMWARE_ADDRESSES.get(lower_name)
        entry = FirmwareEntry(file_path=str(bin_file), address=address or UNKNOWN_BIN_PLACEHOLDER_ADDRESS)
        entry.refresh()
        if address:
            known.append(entry)
        else:
            unknown.append(entry)

    # Sort known entries by their numeric address so bootloader comes first.
    known.sort(key=lambda e: int(e.address, 16))

    result = known + unknown
    logger.info(
        "Auto-detected %d firmware file(s) in %s (%d recognized, %d unknown)",
        len(result), folder_path, len(known), len(unknown),
    )
    return result
