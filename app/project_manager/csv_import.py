"""
csv_import.py
==============
Bulk device import from a CSV file (Devices -> Import Devices from
CSV...). Lets a bench with many devices (e.g. one row per unit off a
production line) populate the device list in one step instead of using
"Add Device" repeatedly and configuring each one by hand.

CSV FORMAT
----------
One header row, then one data row per device. Recognized columns
(case-insensitive, extra/unknown columns are ignored so a spreadsheet
with notes/tracking columns doesn't need to be cleaned up first):

    name        - device display name (required, non-blank)
    com_port    - serial port, e.g. "COM5" or "/dev/ttyUSB0" (optional)
    chip_type   - e.g. "esp32", "esp32s3" (optional, falls back to
                  DEFAULT_CHIP)
    baud_rate   - integer baud rate (optional, falls back to DEFAULT_BAUD)
    tags        - semicolon-separated tags, e.g. "Line A;RFID Batch"
                  (optional)

Only "name" is required. A row missing it, or with a non-integer
baud_rate, is skipped and reported back in CsvImportResult.errors
(1-indexed against the data rows, header excluded) rather than aborting
the whole import -- one bad row in a 200-row CSV shouldn't block the
other 199.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.constants import DEFAULT_BAUD, DEFAULT_CHIP

logger = get_logger(__name__)

_KNOWN_COLUMNS = {"name", "com_port", "chip_type", "baud_rate", "tags"}


@dataclass
class CsvImportResult:
    devices: list[DeviceConfig] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        return len(self.devices)


def import_devices_from_csv(csv_path: str | Path) -> CsvImportResult:
    """Parse `csv_path` and return the devices it describes, plus any
    per-row errors. Never raises for row-level problems -- only for the
    file itself being unreadable/absent, which is a caller-facing setup
    mistake rather than a data-quality issue."""
    path = Path(csv_path)
    result = CsvImportResult()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            result.errors.append("CSV file has no header row.")
            return result

        # Case-insensitive column lookup: build a mapping from lowercased
        # header name back to the CSV's actual header spelling.
        header_map = {h.strip().lower(): h for h in reader.fieldnames if h}

        if "name" not in header_map:
            result.errors.append('CSV file is missing a required "name" column.')
            return result

        for row_number, row in enumerate(reader, start=1):
            try:
                device = _row_to_device(row, header_map)
            except _RowError as exc:
                result.errors.append(f"Row {row_number}: {exc}")
                continue
            if device is not None:
                result.devices.append(device)

    logger.info(
        "CSV import of %s: %d device(s) imported, %d error(s)",
        path, result.imported_count, len(result.errors),
    )
    return result


class _RowError(ValueError):
    pass


def _row_to_device(row: dict, header_map: dict[str, str]) -> DeviceConfig | None:
    def get(column: str) -> str:
        header = header_map.get(column)
        if header is None:
            return ""
        return (row.get(header) or "").strip()

    name = get("name")
    if not name:
        raise _RowError('missing required "name" value')

    baud_raw = get("baud_rate")
    if baud_raw:
        try:
            baud_rate = int(baud_raw)
        except ValueError:
            raise _RowError(f'"baud_rate" value "{baud_raw}" is not an integer') from None
    else:
        baud_rate = DEFAULT_BAUD

    tags_raw = get("tags")
    tags = [t.strip() for t in tags_raw.split(";") if t.strip()] if tags_raw else []

    return DeviceConfig(
        name=name,
        com_port=get("com_port"),
        chip_type=get("chip_type") or DEFAULT_CHIP,
        baud_rate=baud_rate,
        tags=tags,
    )
