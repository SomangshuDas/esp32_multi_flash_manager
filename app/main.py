"""
main.py
=======
Application entry point. Configures logging, installs a global exception
hook so unhandled errors are logged AND shown to the user (never a silent
crash to desktop), and starts the Qt event loop.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.logging_setup.logger import configure_logging, get_logger
from app.ui.main_window import MainWindow
from app.utilities.constants import APP_NAME, ORG_NAME, PROJECT_FILE_EXTENSION
from app.utilities.helpers import resource_path

logger = get_logger(__name__)


class ESPFlashApplication(QApplication):
    """
    QApplication subclass that also catches macOS "open with" / double-click
    events. On Windows and Linux, a file association launch simply appends
    the file path to argv (handled in main() below); macOS instead delivers
    it as a QFileOpenEvent *after* the QApplication is constructed, which is
    why this needs its own event() override rather than an argv check.
    """

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.pending_open_path: str | None = None
        self._main_window: MainWindow | None = None

    def set_main_window(self, window: MainWindow) -> None:
        self._main_window = window
        if self.pending_open_path:
            window.open_project_at_startup(self.pending_open_path)
            self.pending_open_path = None

    def event(self, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if event.type() == QEvent.Type.FileOpen:
            file_path = event.file()
            if self._main_window is not None:
                self._main_window.open_project_at_startup(file_path)
            else:
                self.pending_open_path = file_path
            return True
        return super().event(event)


def _project_path_from_argv(argv: list[str]) -> str | None:
    """
    Pick the first argv entry (after the script name) that looks like a
    `.efmproj` path, ignoring flags like `--debug`. This covers the
    Windows/Linux file-association case: the OS launches the frozen exe as
    `ESP32MultiFlashManager.exe "C:\\path\\to\\project.efmproj"`.
    """
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        candidate = Path(arg)
        if candidate.suffix.lstrip(".").lower() == PROJECT_FILE_EXTENSION:
            return str(candidate)
    return None


def _load_app_icon() -> QIcon:
    """
    Build the application icon from the bundled assets. The SVG gives crisp
    scaling at any size on Linux/macOS; the multi-resolution ICO covers the
    Windows taskbar/Alt-Tab conventions. Both are resolved via
    ``resource_path`` so this also works from a PyInstaller build on any OS.
    """
    icon = QIcon()
    svg_path = resource_path("icons", "app_icon.svg")
    ico_path = resource_path("icons", "app_icon.ico")
    if svg_path.is_file():
        icon.addFile(str(svg_path))
    if ico_path.is_file():
        icon.addFile(str(ico_path))
    return icon


def _install_exception_hook(app: QApplication) -> None:
    """
    Route any unhandled exception to the log AND a message box, instead of
    letting Qt/Python silently kill the app (a hard requirement: 'Never
    crash. Display meaningful errors.').
    """

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.critical("Unhandled exception:\n%s", formatted)
        try:
            QMessageBox.critical(
                None,
                "Unexpected Error",
                "An unexpected error occurred. It has been written to the error log.\n\n"
                f"{exc_type.__name__}: {exc_value}",
            )
        except Exception:  # noqa: BLE001 - message box itself must never crash us further
            pass

    sys.excepthook = handle_exception


def main() -> int:
    log_dir = configure_logging(debug="--debug" in sys.argv)
    logger.info("Starting %s", APP_NAME)

    app = ESPFlashApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(_load_app_icon())

    _install_exception_hook(app)

    window = MainWindow()
    window.show()
    app.set_main_window(window)

    startup_project = _project_path_from_argv(sys.argv)
    if startup_project:
        window.open_project_at_startup(startup_project)

    logger.info("Log directory: %s", log_dir)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
