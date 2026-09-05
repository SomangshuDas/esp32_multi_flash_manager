"""
project_model.py
=================
The top-level "project" object: the full set of configured devices plus
any project-wide metadata. This is what gets serialized to a .emfm
JSON file by project_manager.project_io.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app.models.device_model import DeviceConfig
from app.utilities.constants import APP_VERSION


def _version_tuple(value: str) -> tuple[int, ...]:
    """Small local semver-ish parser (deliberately separate from
    update_checker._parse_version, which additionally has to rank
    pre-release tags below their release -- schema_version comparisons
    here only ever need release-number ordering)."""
    parts = re.findall(r"\d+", str(value))
    return tuple(int(p) for p in parts) or (0,)


# --------------------------------------------------------------------------
# schema_version migration registry.
#
# Previously schema_version was written on every save (defaulting to
# whatever APP_VERSION saved the file) but never read back for anything --
# from_dict() stored it right back onto the new ProjectModel unexamined,
# so it was pure write-only metadata with no actual effect on how an
# older (or, below, a *newer*) file gets loaded. This is genuine,
# exercised plumbing for both directions:
#
#   - MIGRATE: each entry below is a (version_threshold, description,
#     migrate_fn) applied, in order, to the raw dict for any file whose
#     own schema_version compares older than that threshold -- so a
#     structural change introduced in some future release has a real
#     place to register itself instead of leaving old files silently
#     broken/half-migrated. Empty today (nothing has needed a structural
#     migration since schema_version was introduced), but exercised in
#     tests via a registered fake migration so the mechanism itself is
#     proven to run, not just present.
#   - CHECK: a file whose schema_version is NEWER than this build's own
#     APP_VERSION could be missing fields this build doesn't understand
#     yet -- from_dict() now surfaces that as project.schema_warning
#     (see ProjectController) instead of silently proceeding as if
#     nothing were different.
# --------------------------------------------------------------------------
_SCHEMA_MIGRATIONS: list[tuple[tuple[int, ...], str, Callable[[dict], dict]]] = []


@dataclass
class ProjectModel:
    schema_version: str = APP_VERSION
    project_name: str = "Untitled Project"
    devices: list[DeviceConfig] = field(default_factory=list)

    # Window layout is stored as an opaque base64 blob (QMainWindow.saveState)
    window_geometry_b64: str = ""
    window_state_b64: str = ""

    # Transient (never persisted -- absent from to_dict()/from_dict()'s
    # input): set by from_dict() when the loaded file's schema_version is
    # newer than this build's own APP_VERSION, so the controller/UI can
    # surface a "this project was saved by a newer version" notice
    # instead of silently loading a file that may have fields this build
    # doesn't understand.
    schema_warning: str = ""

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
        raw_schema_version = data.get("schema_version", APP_VERSION)
        file_version = _version_tuple(raw_schema_version)

        migrated = dict(data)
        for threshold, _description, migrate_fn in _SCHEMA_MIGRATIONS:
            if file_version < threshold:
                migrated = migrate_fn(migrated)

        schema_warning = ""
        if file_version > _version_tuple(APP_VERSION):
            schema_warning = (
                f"This project was last saved by a newer version ({raw_schema_version}) of this "
                f"app than the one currently running ({APP_VERSION}). Some newer settings may not "
                "be preserved if you save over it with this version."
            )

        return ProjectModel(
            schema_version=raw_schema_version,
            project_name=migrated.get("project_name", "Untitled Project"),
            devices=[DeviceConfig.from_dict(d) for d in migrated.get("devices", [])],
            window_geometry_b64=migrated.get("window_geometry_b64", ""),
            window_state_b64=migrated.get("window_state_b64", ""),
            schema_warning=schema_warning,
        )
