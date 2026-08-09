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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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

    @staticmethod
    def create(device_name: str, com_port: str, firmware_summary: str,
               duration_seconds: float, result: str) -> "HistoryEntry":
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
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "HistoryEntry":
        return HistoryEntry(**data)


def export_history_csv(entries: list[HistoryEntry], destination: str) -> None:
    """Write the given history entries to a CSV file at `destination`."""
    fieldnames = ["date", "time", "device_name", "com_port",
                  "firmware_summary", "duration_seconds", "result"]
    path = Path(destination)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_dict())
