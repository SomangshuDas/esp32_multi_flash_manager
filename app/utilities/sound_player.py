"""
sound_player.py
================
Plays a short notification sound for an app event (flash succeeded/failed,
a whole batch finished, a device connected/disconnected over USB), per the
user's preferences set in Settings -> Sounds.

Built on Qt's own QSoundEffect (part of QtMultimedia, which ships inside
the standard PySide6 PyPI distribution -- no extra dependency needed) so
playback stays cross-platform without shelling out to an OS-specific
player. If the user hasn't picked a custom sound file for an event, this
falls back to QApplication.beep() rather than requiring a bundled asset.

Every function here is defensive: a missing/unreadable sound file, a
missing QtMultimedia audio backend, or any other playback error is logged
and swallowed -- a notification sound failing to play must never interrupt
a flashing job or raise into the UI thread.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from app.logging_setup.logger import get_logger
from app.utilities.app_settings import get_settings
from app.utilities.constants import (
    DEFAULT_ENABLED_SOUND_EVENTS,
    DEFAULT_SOUNDS_ENABLED,
    SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX,
    SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX,
    SETTINGS_KEY_SOUNDS_ENABLED,
)

logger = get_logger(__name__)

# Keeps a strong reference to whatever QSoundEffect is currently playing --
# without this, a locally-scoped QSoundEffect would get garbage-collected
# (and its sound cut off) the instant play_event_sound() returns.
_active_effect = None


def _play_file(path: str) -> bool:
    """Attempt to play `path` via QSoundEffect. Returns True if playback was
    at least started successfully; never raises."""
    global _active_effect
    try:
        from PySide6.QtMultimedia import QSoundEffect
    except ImportError:
        logger.warning("QtMultimedia is unavailable; falling back to system beep")
        return False
    try:
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(path))
        effect.setVolume(0.8)
        effect.play()
        _active_effect = effect
        return True
    except Exception:  # noqa: BLE001 - a notification sound must never crash the app
        logger.exception("Failed to play sound file: %s", path)
        return False


def play_preview_sound(path: str) -> None:
    """Play `path` immediately for the Settings -> Sounds 'Test' button,
    ignoring the enabled/disabled preferences entirely. Falls back to a
    system beep if `path` is blank or fails to play."""
    if not path or not _play_file(path):
        QApplication.beep()


def play_event_sound(event_key: str) -> None:
    """
    Play the configured sound for `event_key` (one of the SOUND_EVENT_*
    constants) if sounds are globally enabled AND this specific event is
    enabled. A silent no-op otherwise. Never raises.
    """
    try:
        settings = get_settings()
        if not settings.value(SETTINGS_KEY_SOUNDS_ENABLED, DEFAULT_SOUNDS_ENABLED, type=bool):
            return
        default_enabled = event_key in DEFAULT_ENABLED_SOUND_EVENTS
        if not settings.value(
            f"{SETTINGS_KEY_SOUND_EVENT_ENABLED_PREFIX}{event_key}", default_enabled, type=bool,
        ):
            return
        path = str(settings.value(f"{SETTINGS_KEY_SOUND_EVENT_PATH_PREFIX}{event_key}", ""))
        if not path or not _play_file(path):
            QApplication.beep()
    except Exception:  # noqa: BLE001 - a notification sound must never crash the app
        logger.exception("Unexpected error while playing sound for event %s", event_key)
