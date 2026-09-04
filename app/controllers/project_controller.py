"""
project_controller.py
======================
Coordinates project lifecycle: new / open / save / save-as, plus
post-load checks for missing firmware files (never fatal — the project
still loads, offending rows are just flagged so the user can relink
them from the Firmware panel).

Legacy `.efmproj` files (the project's file extension prior to the
switch to `.emfm`) can still be opened for backward compatibility, but
are never silently saved back to their old path/format: opening one
leaves `current_file_path` unset, so the very next Save (Ctrl+S) or
autosave routes to Save As instead of quietly overwriting -- see
`open_project()` and `legacy_project_loaded`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel
from app.project_manager.project_io import ProjectLoadError, load_project, save_project
from app.utilities.constants import PROJECT_FILE_EXTENSION_LEGACY

logger = get_logger(__name__)


class ProjectController(QObject):
    """
    Signals
    -------
    project_loaded(ProjectModel)
    project_saved(str)                      - file path
    missing_firmware_detected(list)         - list[FirmwareEntry] that are missing
    load_failed(str)                        - human-readable error message
    legacy_project_loaded(str)              - opened file's original (.efmproj) path;
                                               current_file_path is left unset so the
                                               next save forces a Save As in .emfm
    """

    project_loaded = Signal(object)
    project_saved = Signal(str)
    missing_firmware_detected = Signal(list)
    load_failed = Signal(str)
    legacy_project_loaded = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.project = ProjectModel()
        self.current_file_path: str | None = None
        self.dirty: bool = False

    # ------------------------------------------------------------------
    def new_project(self) -> None:
        self.project = ProjectModel()
        self.current_file_path = None
        self.dirty = False
        self.project_loaded.emit(self.project)
        logger.info("Created new blank project")

    @staticmethod
    def _is_legacy_project_file(file_path: str) -> bool:
        return Path(file_path).suffix.lstrip(".").lower() == PROJECT_FILE_EXTENSION_LEGACY

    def open_project(self, file_path: str) -> bool:
        try:
            project = load_project(file_path)
        except ProjectLoadError as exc:
            logger.error("Project load failed: %s", exc)
            self.load_failed.emit(str(exc))
            return False

        is_legacy = self._is_legacy_project_file(file_path)
        self.project = project
        # A legacy .efmproj file is opened read-only as far as its ORIGINAL
        # path is concerned -- leaving current_file_path unset means
        # save_project()/the UI's "Save" action (see MainWindow._on_save_project)
        # has no path to silently reuse and falls through to Save As,
        # forcing the user to pick a new .emfm location/name rather than
        # ever overwriting the old file in the old format.
        self.current_file_path = None if is_legacy else file_path
        self.dirty = is_legacy
        self.project_loaded.emit(self.project)

        if is_legacy:
            logger.info("Opened legacy .%s project %s -- Save As required", PROJECT_FILE_EXTENSION_LEGACY, file_path)
            self.legacy_project_loaded.emit(file_path)

        missing = self._collect_missing_firmware(project)
        if missing:
            self.missing_firmware_detected.emit(missing)
        return True

    def save_project(self, file_path: str | None = None) -> bool:
        target = file_path or self.current_file_path
        if not target:
            logger.warning("save_project called with no target path")
            return False
        try:
            save_project(self.project, target)
        except ProjectLoadError as exc:
            self.load_failed.emit(str(exc))
            return False
        self.current_file_path = target
        self.dirty = False
        self.project_saved.emit(target)
        return True

    def mark_dirty(self) -> None:
        self.dirty = True

    @staticmethod
    def _collect_missing_firmware(project: ProjectModel) -> list[FirmwareEntry]:
        missing: list[FirmwareEntry] = []
        for device in project.devices:
            for entry in device.firmware:
                if entry.missing:
                    missing.append(entry)
        return missing
