"""
diagnostics.py
================
"Export Diagnostics Bundle" (Help -> Export Diagnostics Bundle...): packages
the four rotating log files (plus events.jsonl, if JSON logging is enabled)
together with application/OS/Python/esptool version information into a
single zip file, so a bug report can attach one file instead of the user
hunting down and attaching several individually.

Nothing here is telemetry -- this is a manual, explicit, one-shot export
the user triggers and saves wherever they choose; it never runs on its own
and nothing is uploaded anywhere by this app.
"""

from __future__ import annotations

import json
import platform
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.logging_setup.logger import get_logger
from app.utilities.constants import APP_NAME, APP_VERSION, JSON_LOG_FILENAME
from app.utilities.helpers import get_app_data_dir

logger = get_logger(__name__)

_LOG_FILENAMES = ("application.log", "flash.log", "error.log", "debug.log", JSON_LOG_FILENAME)


@dataclass
class DiagnosticsInfo:
    """Version/environment metadata bundled alongside the raw log files."""

    app_name: str
    app_version: str
    os_name: str
    os_version: str
    python_version: str
    esptool_version: str | None
    generated_at: str
    included_logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "python_version": self.python_version,
            "esptool_version": self.esptool_version,
            "generated_at": self.generated_at,
            "included_logs": self.included_logs,
        }


def _detect_esptool_version() -> str | None:
    try:
        from esptool import __version__ as esptool_version  # type: ignore[import-not-found]

        return str(esptool_version)
    except Exception:  # noqa: BLE001 - esptool missing/broken must not block the export
        return None


def collect_diagnostics_info(log_dir: Path | None = None) -> DiagnosticsInfo:
    log_dir = log_dir or (get_app_data_dir() / "logs")
    included = [name for name in _LOG_FILENAMES if (log_dir / name).is_file()]
    return DiagnosticsInfo(
        app_name=APP_NAME,
        app_version=APP_VERSION,
        os_name=platform.system() or "unknown",
        os_version=platform.version() or "unknown",
        python_version=platform.python_version(),
        esptool_version=_detect_esptool_version(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        included_logs=included,
    )


def export_diagnostics_bundle(dest_path: str | Path, log_dir: Path | None = None) -> Path:
    """Write a zip file at `dest_path` containing every existing log file
    plus a diagnostics_info.json manifest. Returns the resolved path
    written. Missing individual log files (e.g. debug logging was never
    enabled) are silently skipped rather than treated as an error --
    a partial bundle is still useful for a bug report.
    """
    log_dir = log_dir or (get_app_data_dir() / "logs")
    info = collect_diagnostics_info(log_dir)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("diagnostics_info.json", json.dumps(info.to_dict(), indent=2))
        for name in info.included_logs:
            file_path = log_dir / name
            try:
                bundle.write(file_path, arcname=f"logs/{name}")
            except OSError:
                logger.exception("Failed to add %s to diagnostics bundle", file_path)

    logger.info("Diagnostics bundle written to %s (%d logs included)", dest_path, len(info.included_logs))
    return dest_path
