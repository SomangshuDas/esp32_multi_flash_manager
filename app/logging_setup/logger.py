"""
logger.py
=========
Centralized logging configuration.

The application maintains FOUR separate rotating log files, as required by
the spec:

    application.log  - general lifecycle / UI events
    flash.log        - everything related to flashing operations
    error.log        - ERROR and CRITICAL records only (from any logger)
    debug.log        - full DEBUG-level firehose, useful for support tickets

All logs live under the per-user app-data directory so the application
never needs write access to its install location (important for
manufacturing-floor PCs that are often locked down).
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.utilities.helpers import get_app_data_dir

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _make_rotating_handler(path: Path, level: int) -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        filename=str(path),
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    return handler


def configure_logging(debug: bool = False) -> Path:
    """
    Configure the root logger with rotating file handlers plus a console
    handler. Safe to call multiple times (subsequent calls are no-ops).

    Returns the directory where log files are stored, so the UI can offer
    an "Open Logs Folder" action.
    """
    global _CONFIGURED
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if _CONFIGURED:
        return log_dir

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # application.log - INFO and above, general app events
    app_handler = _make_rotating_handler(log_dir / "application.log", logging.INFO)

    # flash.log - only records coming from the flash_engine / workers loggers
    flash_handler = _make_rotating_handler(log_dir / "flash.log", logging.DEBUG)
    flash_handler.addFilter(
        lambda record: record.name.startswith("app.flash_engine")
        or record.name.startswith("app.workers")
    )

    # error.log - ERROR and CRITICAL from anywhere
    error_handler = _make_rotating_handler(log_dir / "error.log", logging.ERROR)

    # debug.log - everything, for deep troubleshooting
    debug_handler = _make_rotating_handler(log_dir / "debug.log", logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    for handler in (app_handler, flash_handler, error_handler, debug_handler, console_handler):
        root.addHandler(handler)

    _CONFIGURED = True
    logging.getLogger(__name__).info("Logging initialized. Log directory: %s", log_dir)
    return log_dir


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper so callers don't need to import logging directly."""
    return logging.getLogger(name)
