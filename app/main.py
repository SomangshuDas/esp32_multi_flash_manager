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

# --------------------------------------------------------------------------
# esptool re-exec fast path -- checked FIRST, before any PySide6/app.ui
# imports, and using only the stdlib. This matters for frozen (PyInstaller)
# builds: `sys.executable` there is this app's own .exe, so the flash engine
# launches N of these subprocesses in parallel (one per device) with a
# hidden flag instead of shelling out to a Python interpreter that doesn't
# exist on the target machine. Each of those subprocess launches must skip
# Qt/GUI import overhead entirely and go straight to esptool, or parallel
# flashing of several devices would be needlessly slow.
# --------------------------------------------------------------------------
_ESPTOOL_REEXEC_FLAG = "--_run-esptool"

if _ESPTOOL_REEXEC_FLAG in sys.argv:
    import io
    # PyInstaller's --windowed bootloader sometimes nulls sys.stdout/stderr
    # even when the parent process (FlashProcess, see esptool_wrapper.py)
    # supplied real pipe handles via subprocess.Popen(stdout=PIPE). Rebind
    # them to the raw OS file descriptors so esptool's progress output is
    # never silently swallowed.
    if sys.stdout is None:
        sys.stdout = io.TextIOWrapper(io.FileIO(1, "w"), write_through=True)
    if sys.stderr is None:
        sys.stderr = io.TextIOWrapper(io.FileIO(2, "w"), write_through=True)
    import esptool
    sys.argv = [a for a in sys.argv if a != _ESPTOOL_REEXEC_FLAG]
    sys.exit(esptool.main(sys.argv[1:]))

from PySide6.QtCore import QEvent, QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.logging_setup.logger import configure_logging, get_logger
from app.ui.main_window import MainWindow
from app.utilities.constants import APP_NAME, ESPTOOL_REEXEC_FLAG, ORG_NAME, PROJECT_FILE_EXTENSION
from app.utilities.helpers import get_app_data_dir, resource_path

assert ESPTOOL_REEXEC_FLAG == _ESPTOOL_REEXEC_FLAG, (
    "app.utilities.constants.ESPTOOL_REEXEC_FLAG must match main.py's fast-path "
    "flag string, or the flash engine and this entry point will disagree."
)

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


def _acquire_single_instance_lock() -> QLockFile | None:
    """
    Take an exclusive lock on a file in the app-data folder so a second
    launch of the app can detect a first one is already running (rather
    than opening a confusing second window pointed at the same devices/
    settings.json). Returns the held QLockFile (keep it referenced for the
    app's whole lifetime — it releases automatically when garbage
    collected or the process exits), or None if another instance already
    holds it.
    """
    lock_path = get_app_data_dir() / "app.lock"
    lock_file = QLockFile(str(lock_path))
    lock_file.setStaleLockTime(0)  # a lock left by a crashed process never blocks forever
    if lock_file.tryLock(100):
        return lock_file
    return None


def main() -> int:
    log_dir = configure_logging(debug="--debug" in sys.argv)
    logger.info("Starting %s", APP_NAME)

    app = ESPFlashApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(_load_app_icon())

    _install_exception_hook(app)

    instance_lock = _acquire_single_instance_lock()
    if instance_lock is None:
        logger.warning("Another instance is already running; exiting.")
        QMessageBox.warning(
            None, APP_NAME,
            f"{APP_NAME} is already running.\n\nOnly one instance can run at a time.",
        )
        return 1
    app.instance_lock = instance_lock  # keep it alive for the process lifetime

    window = MainWindow()
    window.show_startup()
    app.set_main_window(window)

    startup_project = _project_path_from_argv(sys.argv)
    if startup_project:
        window.open_project_at_startup(startup_project)

    logger.info("Log directory: %s", log_dir)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
