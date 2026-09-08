"""
telemetry.py
=============
Opt-in, anonymous usage and crash telemetry.

WHAT THIS DOES
--------------
When enabled (Settings -> Privacy -> "Share anonymous usage & crash data",
OFF by default), the app records a small number of coarse events --
things like "a flash batch finished" or "an unhandled exception occurred"
-- to a local, rotating JSON-lines file under the app-data folder
(TELEMETRY_LOG_FILENAME). Each event carries only:

    - a random per-install client id (generated once, stored in
      settings.json, never derived from anything identifying)
    - an event name (from a fixed, reviewed set -- see TelemetryEvent)
    - a small dict of event-specific counters/booleans (e.g. device
      count, success/failure counts, elapsed seconds) -- NEVER device
      serial numbers, COM port names, firmware file paths/names, project
      names, or anything else that could identify a person, a device, or
      the content being flashed
    - a UTC timestamp

WHAT THIS DELIBERATELY DOES NOT DO (yet)
-----------------------------------------
This build does not transmit telemetry over the network anywhere. Events
are written locally only. Shipping a real collection backend is a
separate, larger decision (choosing/standing up an endpoint, a retention
policy, a privacy-facing disclosure of where data actually goes) that is
out of scope for this change -- see ROADMAP.md. record_event() is the
single call site a future release would extend to also POST the same
payload to a configured endpoint; nothing else in the app needs to
change.

See docs/PRIVACY.md for the user-facing disclosure of what is collected
once a user opts in, and Settings -> Privacy for the toggle itself.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.logging_setup.logger import get_logger
from app.utilities.constants import SETTINGS_KEY_TELEMETRY_CLIENT_ID, TELEMETRY_LOG_FILENAME
from app.utilities.helpers import get_app_data_dir, new_uuid

logger = get_logger(__name__)

_MAX_TELEMETRY_FILE_BYTES = 2 * 1024 * 1024  # rotate/truncate well before this grows unbounded
_write_lock = threading.Lock()


class TelemetryEvent(str, Enum):
    """Fixed, reviewed set of event names. Deliberately closed (not
    free-text) so no call site can accidentally smuggle identifying
    information into the event *name* itself."""

    APP_STARTED = "app_started"
    FLASH_BATCH_FINISHED = "flash_batch_finished"
    PROVISION_BATCH_FINISHED = "provision_batch_finished"
    PROJECT_OPENED = "project_opened"
    PROJECT_SAVED = "project_saved"
    UNHANDLED_EXCEPTION = "unhandled_exception"


@dataclass
class _TelemetryState:
    enabled: bool = False
    client_id: str = ""


_state = _TelemetryState()
_state_lock = threading.Lock()


def _get_client_id() -> str:
    """Return the per-install anonymous client id, generating and
    persisting one on first use. Deferred import of app_settings avoids a
    circular import at module load time."""
    from app.utilities.app_settings import get_settings

    settings = get_settings()
    client_id = settings.value(SETTINGS_KEY_TELEMETRY_CLIENT_ID, "", type=str)
    if not client_id:
        client_id = new_uuid()
        settings.setValue(SETTINGS_KEY_TELEMETRY_CLIENT_ID, client_id)
    return client_id


def is_enabled() -> bool:
    from app.utilities.app_settings import get_telemetry_enabled

    return get_telemetry_enabled()


def _telemetry_path() -> Path:
    return get_app_data_dir() / TELEMETRY_LOG_FILENAME


def _truncate_if_needed(path: Path) -> None:
    """Keep the local telemetry file from growing without bound. Not a
    real rotating-file-handler setup (this file is written to directly,
    not through logging), so this is a simple "drop the oldest half"
    truncation instead."""
    try:
        if not path.exists() or path.stat().st_size < _MAX_TELEMETRY_FILE_BYTES:
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        keep = lines[len(lines) // 2 :]
        path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    except OSError:
        logger.exception("Failed to truncate telemetry file %s", path)


def record_event(event: TelemetryEvent, data: dict[str, Any] | None = None) -> None:
    """Record one telemetry event, if and only if telemetry is enabled.

    Safe to call unconditionally from any call site regardless of the
    current setting -- this is a no-op (and does not touch disk at all)
    when telemetry is disabled, so instrumenting a new call site never
    itself creates a privacy concern; the opt-in gate is centralized
    here, not duplicated at every call site.
    """
    if not is_enabled():
        return
    payload = {
        "client_id": _get_client_id(),
        "event": event.value,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path = _telemetry_path()
    try:
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            _truncate_if_needed(path)
    except OSError:
        logger.exception("Failed to write telemetry event %s", event.value)


def clear_local_telemetry() -> None:
    """Delete the local telemetry file entirely (Settings -> Privacy ->
    "Clear local telemetry data"). Never fails loudly -- deleting
    something that doesn't exist yet is not an error from the user's
    point of view."""
    path = _telemetry_path()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logger.exception("Failed to clear telemetry file %s", path)
