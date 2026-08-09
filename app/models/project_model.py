"""
project_model.py
=================
The top-level "project" object: the full set of configured devices plus
any project-wide metadata. This is what gets serialized to a .efmproj
JSON file by project_manager.project_io.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.device_model import DeviceConfig
from app.utilities.constants import APP_VERSION


@dataclass
class ProjectModel:
    schema_version: str = APP_VERSION
    project_name: str = "Untitled Project"
    devices: list[DeviceConfig] = field(default_factory=list)

    # Window layout is stored as an opaque base64 blob (QMainWindow.saveState)
    window_geometry_b64: str = ""
    window_state_b64: str = ""

    def add_device(self, device: DeviceConfig) -> None:
        self.devices.append(device)

    def remove_device(self, device_id: str) -> None:
        self.devices = [d for d in self.devices if d.id != device_id]

    def find_device(self, device_id: str) -> DeviceConfig | None:
        return next((d for d in self.devices if d.id == device_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_name": self.project_name,
            "devices": [d.to_dict() for d in self.devices],
            "window_geometry_b64": self.window_geometry_b64,
            "window_state_b64": self.window_state_b64,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ProjectModel":
        return ProjectModel(
            schema_version=data.get("schema_version", APP_VERSION),
            project_name=data.get("project_name", "Untitled Project"),
            devices=[DeviceConfig.from_dict(d) for d in data.get("devices", [])],
            window_geometry_b64=data.get("window_geometry_b64", ""),
            window_state_b64=data.get("window_state_b64", ""),
        )
