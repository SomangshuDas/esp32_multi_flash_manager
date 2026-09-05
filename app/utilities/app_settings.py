"""
app_settings.py
================
JSON-backed replacement for QSettings.

Every persisted app preference — theme, default baud rate, default flash
mode, window geometry/state, the recent-projects list — is written to a
single ``settings.json`` file under the per-user roaming app-data
directory (see ``get_app_data_dir()``) instead of the Windows registry
(or macOS .plist / Linux .ini) that QSettings would otherwise use. This
keeps the entire application footprint under one folder on every
platform, which is also what makes a clean "keep my data / remove
everything" uninstall choice possible.

The public API intentionally mirrors the small subset of QSettings that
this app actually used (``value`` / ``setValue``) so call sites did not
need to change beyond swapping the import.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray

from app.logging_setup.logger import get_logger
from app.utilities.constants import (
    FLASH_STALL_TIMEOUT_MAX_SECONDS,
    FLASH_STALL_TIMEOUT_MIN_SECONDS,
    FLASH_STALL_TIMEOUT_SECONDS,
    SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS,
)
from app.utilities.helpers import clear_file_hidden, get_app_data_dir, mark_file_hidden

logger = get_logger(__name__)

SETTINGS_FILENAME = "settings.json"

# QByteArray values (window geometry/state) cannot be serialized to JSON
# directly; they are stored as base64 text tagged with this marker key so
# they round-trip back into a real QByteArray on load.
_QBYTEARRAY_MARKER = "__qbytearray_b64__"


def _encode(value: Any) -> Any:
    if isinstance(value, QByteArray):
        return {_QBYTEARRAY_MARKER: base64.b64encode(bytes(value)).decode("ascii")}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and _QBYTEARRAY_MARKER in value:
        return QByteArray(base64.b64decode(value[_QBYTEARRAY_MARKER]))
    return value


class AppSettings:
    """Minimal QSettings-like key/value store backed by one JSON file."""

    def __init__(self) -> None:
        self._path: Path = get_app_data_dir() / SETTINGS_FILENAME
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read %s; falling back to defaults", self._path)
            return {}

    def _save(self) -> None:
        """
        Write settings.json atomically: serialize to a temp file in the
        same directory, flush+fsync it, then os.replace() it over the
        real path. os.replace is atomic on both POSIX and Windows, so a
        crash/power-loss/kill mid-write can never leave settings.json
        half-written/truncated (the previous direct
        ``self._path.open("w")`` could -- corrupting every persisted
        preference including the recent-projects list and window
        geometry, discovered only on the next launch).
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_name(f".{self._path.name}.tmp-{os.getpid()}")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            mark_file_hidden(tmp_path)
            os.replace(tmp_path, self._path)
            clear_file_hidden(self._path)
        except OSError:
            logger.exception("Failed to write %s", self._path)
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)

    def value(self, key: str, default: Any = None, type: type | None = None) -> Any:
        with self._lock:
            raw = self._data.get(key, default)
        result = _decode(raw)
        if type is not None and result is not None and not isinstance(result, type):
            try:
                if type is bool:
                    result = str(result).strip().lower() in ("1", "true", "yes")
                else:
                    result = type(result)
            except (TypeError, ValueError):
                return default
        return result

    def setValue(self, key: str, value: Any) -> None:  # noqa: N802 - mirrors QSettings' API
        with self._lock:
            self._data[key] = _encode(value)
            self._save()

    def remove(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._save()


_instance: AppSettings | None = None
_instance_lock = threading.Lock()


def get_settings() -> AppSettings:
    """Return the single process-wide AppSettings instance, created on first use."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AppSettings()
        return _instance


def get_flash_stall_timeout_seconds() -> float:
    """
    Return the configured stall-detection timeout (in seconds) used by
    both FlashWorker and ReadWorker to decide a device has stopped
    responding (see Settings -> General -> "Flash stall timeout").

    Previously FLASH_STALL_TIMEOUT_SECONDS was a hardcoded constant with
    no way to change it without editing source and rebuilding -- some
    boards/USB-serial adapters/OS combinations legitimately need a
    longer grace period (e.g. a slow erase of a large external flash
    chip) than others need for a *shorter* one (faster failure feedback
    on a bench with many devices). Falls back to the
    FLASH_STALL_TIMEOUT_SECONDS default, and clamps to
    [FLASH_STALL_TIMEOUT_MIN_SECONDS, FLASH_STALL_TIMEOUT_MAX_SECONDS] so
    a corrupted/hand-edited settings.json value can't produce a
    nonsensical (zero, negative, or absurdly long) timeout.
    """
    settings = get_settings()
    try:
        value = float(
            settings.value(SETTINGS_KEY_FLASH_STALL_TIMEOUT_SECONDS, FLASH_STALL_TIMEOUT_SECONDS)
        )
    except (TypeError, ValueError):
        return FLASH_STALL_TIMEOUT_SECONDS
    if value != value:  # NaN guard (NaN != NaN)
        return FLASH_STALL_TIMEOUT_SECONDS
    return max(FLASH_STALL_TIMEOUT_MIN_SECONDS, min(FLASH_STALL_TIMEOUT_MAX_SECONDS, value))
