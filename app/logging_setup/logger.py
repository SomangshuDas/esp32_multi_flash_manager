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

Optionally, a FIFTH rotating log -- events.jsonl -- mirrors every record
as one JSON object per line, alongside (never instead of) the four text
logs above. This is off by default (Settings -> Diagnostics -> "Enable
structured JSON logging") since the text logs remain the primary,
always-on format; JSON output exists for anyone piping logs into a
log-aggregation/SIEM tool that expects structured records. See
JsonLinesFormatter below and app.utilities.app_settings.get_json_logging_enabled.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path

from app.utilities.helpers import get_app_data_dir

_CONFIGURED = False


class JsonLinesFormatter(logging.Formatter):
    """Renders each LogRecord as a single JSON object (one per line).

    Deliberately minimal and dependency-free (no third-party JSON-logging
    library) -- just enough structure (timestamp, level, logger name,
    message, and exception info when present) to be useful to a log
    aggregator without pulling in a new dependency for something this
    small.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

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

    _maybe_add_json_handler(root, log_dir)

    _CONFIGURED = True
    logging.getLogger(__name__).info("Logging initialized. Log directory: %s", log_dir)
    return log_dir


def _maybe_add_json_handler(root: logging.Logger, log_dir: Path) -> None:
    """Attach the optional events.jsonl handler if the user has enabled it
    in Settings -> Diagnostics. Import of app_settings is deferred to
    avoid a module-level circular import (app_settings itself only needs
    get_logger, not configure_logging)."""
    try:
        from app.utilities.app_settings import get_json_logging_enabled
        from app.utilities.constants import JSON_LOG_FILENAME
    except ImportError:  # pragma: no cover - defensive, shouldn't happen
        return
    if not get_json_logging_enabled():
        return
    json_handler = _make_rotating_handler(log_dir / JSON_LOG_FILENAME, logging.DEBUG)
    json_handler.setFormatter(JsonLinesFormatter())
    root.addHandler(json_handler)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper so callers don't need to import logging directly."""
    return logging.getLogger(name)
