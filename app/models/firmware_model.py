"""
firmware_model.py
==================
Data model for a single firmware binary (.bin) entry attached to a device.
Deliberately a plain dataclass (no QObject) so it can be freely
serialized to JSON for project files and copied/duplicated cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utilities.helpers import compute_md5, file_exists, human_readable_size, new_uuid


@dataclass
class FirmwareEntry:
    """A single BIN file plus the address it should be flashed to."""

    id: str = field(default_factory=new_uuid)
    file_path: str = ""
    address: str = "0x1000"
    enabled: bool = True

    # Cached, derived fields (recomputed via refresh()) — not authoritative,
    # but persisted so the UI has something to show before a refresh runs.
    file_size: int = 0
    md5: str = ""
    missing: bool = False

    @property
    def file_name(self) -> str:
        import os
        return os.path.basename(self.file_path) if self.file_path else "(no file)"

    @property
    def display_size(self) -> str:
        return human_readable_size(self.file_size) if self.file_size else "-"

    def refresh(self) -> None:
        """Recompute size/MD5/missing status from disk. Never raises."""
        if not file_exists(self.file_path):
            self.missing = True
            self.file_size = 0
            self.md5 = ""
            return
        try:
            import os
            self.missing = False
            self.file_size = os.path.getsize(self.file_path)
            self.md5 = compute_md5(self.file_path)
        except OSError:
            self.missing = True
            self.file_size = 0
            self.md5 = ""

    def duplicate(self) -> "FirmwareEntry":
        """Return a deep copy with a new unique id (used by 'Duplicate BIN')."""
        return FirmwareEntry(
            id=new_uuid(),
            file_path=self.file_path,
            address=self.address,
            enabled=self.enabled,
            file_size=self.file_size,
            md5=self.md5,
            missing=self.missing,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "address": self.address,
            "enabled": self.enabled,
            "file_size": self.file_size,
            "md5": self.md5,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FirmwareEntry":
        entry = FirmwareEntry(
            id=data.get("id", new_uuid()),
            file_path=data.get("file_path", ""),
            address=data.get("address", "0x1000"),
            enabled=data.get("enabled", True),
            file_size=data.get("file_size", 0),
            md5=data.get("md5", ""),
        )
        entry.refresh()
        return entry
