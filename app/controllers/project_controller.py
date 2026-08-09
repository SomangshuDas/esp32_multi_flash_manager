"""
project_controller.py
======================
Coordinates project lifecycle: new / open / save / save-as, plus
post-load checks for missing firmware files (never fatal — the project
still loads, offending rows are just flagged so the user can relink
them from the Firmware panel).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.models.project_model import ProjectModel
from app.project_manager.project_io import ProjectLoadError, load_project, save_project

logger = get_logger(__name__)


class ProjectController(QObject):
    """
    Signals
    -------
    project_loaded(ProjectModel)
    project_saved(str)                      - file path
    missing_firmware_detected(list)         - list[FirmwareEntry] that are missing
    load_failed(str)                        - human-readable error message
    """

    project_loaded = Signal(object)
    project_saved = Signal(str)
    missing_firmware_detected = Signal(list)
    load_failed = Signal(str)

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

    def open_project(self, file_path: str) -> bool:
        try:
            project = load_project(file_path)
        except ProjectLoadError as exc:
            logger.error("Project load failed: %s", exc)
            self.load_failed.emit(str(exc))
            return False

        self.project = project
        self.current_file_path = file_path
        self.dirty = False
        self.project_loaded.emit(self.project)

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
