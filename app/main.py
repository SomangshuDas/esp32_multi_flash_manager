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

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.logging_setup.logger import configure_logging, get_logger
from app.ui.main_window import MainWindow
from app.utilities.constants import APP_NAME, ORG_NAME
from app.utilities.helpers import resource_path

logger = get_logger(__name__)


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

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(_load_app_icon())

    _install_exception_hook(app)

    window = MainWindow()
    window.show()

    logger.info("Log directory: %s", log_dir)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
