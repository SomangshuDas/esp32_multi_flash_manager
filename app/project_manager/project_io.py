"""
project_io.py
==============
Handles saving and loading .efmproj project files (plain JSON), plus the
"recent projects" list persisted via AppSettings. Designed to never raise
an uncaught exception into the UI layer — callers get either a valid
ProjectModel or a ProjectLoadError with a human-readable message.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.logging_setup.logger import get_logger
from app.models.project_model import ProjectModel
from app.utilities.app_settings import get_settings
from app.utilities.constants import MAX_RECENT_PROJECTS

logger = get_logger(__name__)


class ProjectLoadError(Exception):
    """Raised when a project file cannot be parsed or is structurally invalid."""


def save_project(project: ProjectModel, file_path: str) -> None:
    """Serialize `project` to `file_path` as pretty-printed JSON."""
    path = Path(file_path)
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(project.to_dict(), handle, indent=2, ensure_ascii=False)
        logger.info("Project saved to %s (%d devices)", file_path, len(project.devices))
        add_recent_project(file_path)
    except OSError as exc:
        logger.exception("Failed to save project to %s", file_path)
        raise ProjectLoadError(f"Could not write project file:\n{exc}") from exc


def load_project(file_path: str) -> ProjectModel:
    """
    Load a .efmproj file. Missing firmware files are NOT treated as fatal —
    the caller (controller) is responsible for validating firmware paths
    afterwards and surfacing warnings; a corrupt/unreadable JSON file *is*
    fatal and raises ProjectLoadError.
    """
    path = Path(file_path)
    if not path.is_file():
        raise ProjectLoadError(f"Project file not found:\n{file_path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Failed to parse project file %s", file_path)
        raise ProjectLoadError(
            f"This project file is corrupted or not valid JSON:\n{exc}"
        ) from exc

    try:
        project = ProjectModel.from_dict(raw)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, never crash UI
        logger.exception("Failed to build ProjectModel from %s", file_path)
        raise ProjectLoadError(
            f"This project file's structure is not recognized:\n{exc}"
        ) from exc

    # Refresh firmware metadata (size/MD5/missing) for every device.
    for device in project.devices:
        for entry in device.firmware:
            entry.refresh()

    logger.info("Project loaded from %s (%d devices)", file_path, len(project.devices))
    add_recent_project(file_path)
    return project


# --------------------------------------------------------------------------
# Recent projects (persisted via AppSettings, a single settings.json file
# under the per-user roaming app-data folder — no registry involvement on
# any platform).
# --------------------------------------------------------------------------
def add_recent_project(file_path: str) -> None:
    settings = get_settings()
    recents: list[str] = settings.value("recent_projects", [], type=list) or []
    recents = [p for p in recents if p != file_path]
    recents.insert(0, file_path)
    recents = recents[:MAX_RECENT_PROJECTS]
    settings.setValue("recent_projects", recents)


def get_recent_projects() -> list[str]:
    settings = get_settings()
    recents: list[str] = settings.value("recent_projects", [], type=list) or []
    # Filter out projects that no longer exist on disk.
    return [p for p in recents if Path(p).is_file()]


def clear_recent_projects() -> None:
    get_settings().setValue("recent_projects", [])
