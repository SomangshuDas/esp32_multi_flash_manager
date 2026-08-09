"""
helpers.py
==========
Small, dependency-free utility functions shared across the application.
Nothing in this module should import from ``app.ui`` — it must stay usable
from headless contexts (workers, tests, CLI tools).
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path


def new_uuid() -> str:
    """Return a fresh unique identifier string used for devices/firmware rows."""
    return str(uuid.uuid4())


def compute_md5(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    Compute the MD5 checksum of a file, streaming it in chunks so that even
    large firmware images (multi-MB) do not blow up memory usage.

    Raises FileNotFoundError / OSError if the file cannot be read; callers
    are expected to handle that (e.g. to mark firmware rows as "missing").
    """
    md5 = hashlib.md5()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def human_readable_size(num_bytes: int) -> str:
    """Convert a byte count into a human friendly string, e.g. '1.4 MB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def human_readable_duration(seconds: float) -> str:
    """Convert a duration in seconds into 'HH:MM:SS' or 'MM:SS' string form."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def is_valid_hex_address(value: str) -> bool:
    """Return True if `value` looks like a valid flash address, e.g. '0x10000'."""
    if not value:
        return False
    return bool(re.fullmatch(r"0[xX][0-9a-fA-F]+", value.strip()))


def normalize_hex_address(value: str) -> str:
    """Normalize a hex address string to lowercase with a single '0x' prefix."""
    value = value.strip()
    if not value.lower().startswith("0x"):
        value = "0x" + value
    return "0x" + value[2:].lower().lstrip("x")


def file_exists(path: str | None) -> bool:
    """Safe existence check that tolerates None / empty strings."""
    if not path:
        return False
    return Path(path).is_file()


def timestamp_now() -> str:
    """Return the current timestamp formatted for logs and history entries."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename(name: str) -> str:
    """Strip characters that are illegal in filenames on Windows (a superset
    of what's illegal on macOS/Linux), so a safe name works on every OS."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "unnamed"


def get_app_data_dir() -> Path:
    """
    Return (and create if needed) the per-user application data directory,
    following each platform's own convention rather than a single
    Windows-shaped fallback:

        Windows -> %APPDATA%\\ESP32MultiFlashManager
        macOS   -> ~/Library/Application Support/ESP32MultiFlashManager
        Linux   -> $XDG_DATA_HOME/ESP32MultiFlashManager
                   (or ~/.local/share/ESP32MultiFlashManager if XDG_DATA_HOME
                   is not set, per the XDG Base Directory spec)

    This is what stores settings, recent projects, firmware profiles, and
    the rotating log files — never the application's own install directory,
    so the app never needs write access to wherever it's installed.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"

    target = base / "ESP32MultiFlashManager"
    target.mkdir(parents=True, exist_ok=True)
    return target


def resource_path(*parts: str) -> Path:
    """
    Resolve a path under the ``resources/`` directory that works identically:

      - running from source (``python run.py`` from the project root)
      - packaged with PyInstaller in ``--onefile`` mode, where bundled data
        is unpacked to a temporary directory exposed as ``sys._MEIPASS``
      - packaged with PyInstaller in ``--onedir`` mode, where bundled data
        sits next to the executable

    Always use this instead of hardcoding ``"resources/..."`` so icons and
    themes keep working after packaging on every OS.
    """
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # app/utilities/helpers.py -> app/utilities -> app -> project root
        base = Path(__file__).resolve().parent.parent.parent
    return base.joinpath("resources", *parts)
