"""
history_model.py
=================
Represents one row of the persistent flash-history log: a single flashing
attempt for a single device, along with its outcome. Used to populate the
History panel and to export CSV reports for quality/traceability purposes
on the manufacturing floor.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utilities.constants import QC_STATUS_NOT_TESTED
from app.utilities.helpers import timestamp_now


@dataclass
class HistoryEntry:
    date: str
    time: str
    device_name: str
    com_port: str
    firmware_summary: str
    duration_seconds: float
    result: str  # Completed / Failed / Cancelled

    # Added for QC Verification / Device Traceability. Defaulted so older
    # project/history files (saved before these fields existed) still load
    # fine via from_dict -- missing keys just fall back to these defaults.
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    device_id: str = ""
    mac_address: str = ""
    qc_status: str = QC_STATUS_NOT_TESTED

    @staticmethod
    def create(device_name: str, com_port: str, firmware_summary: str,
               duration_seconds: float, result: str, device_id: str = "",
               mac_address: str = "") -> "HistoryEntry":
        now = timestamp_now()
        date_part, time_part = now.split(" ")
        return HistoryEntry(
            date=date_part,
            time=time_part,
            device_name=device_name,
            com_port=com_port,
            firmware_summary=firmware_summary,
            duration_seconds=round(duration_seconds, 1),
            result=result,
            device_id=device_id,
            mac_address=mac_address,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "HistoryEntry":
        # Filter to known dataclass fields only, so a stray/future key in an
        # old or hand-edited history file doesn't blow up loading.
        known = {f for f in HistoryEntry.__dataclass_fields__}
        return HistoryEntry(**{k: v for k, v in data.items() if k in known})


def export_history_csv(entries: list[HistoryEntry], destination: str) -> None:
    """Write the given history entries to a CSV file at `destination`."""
    fieldnames = ["date", "time", "device_name", "com_port", "mac_address",
                  "firmware_summary", "duration_seconds", "result", "qc_status"]
    path = Path(destination)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = entry.to_dict()
            writer.writerow({k: row.get(k, "") for k in fieldnames})
