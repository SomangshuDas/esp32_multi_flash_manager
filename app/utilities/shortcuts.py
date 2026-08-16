"""
shortcuts.py
============
User-customisable keyboard shortcuts. Defaults live in
``app.utilities.constants.DEFAULT_SHORTCUTS``; any remapping the user
makes via Tools -> Keyboard Shortcuts... is stored as an override in
AppSettings (only the entries that differ from default are persisted),
so a future release that changes a default is picked up automatically
for anyone who never touched that particular shortcut.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence

from app.utilities.app_settings import get_settings
from app.utilities.constants import DEFAULT_SHORTCUTS, SETTINGS_KEY_CUSTOM_SHORTCUTS


def get_shortcuts() -> dict[str, str]:
    """Return {action_id: key_sequence_string} for every customisable
    action, defaults merged with any saved overrides."""
    settings = get_settings()
    overrides = settings.value(SETTINGS_KEY_CUSTOM_SHORTCUTS, {}, type=dict) or {}
    merged = dict(DEFAULT_SHORTCUTS)
    for action_id, key_sequence in overrides.items():
        if action_id in merged:
            merged[action_id] = key_sequence
    return merged


def save_shortcuts(mapping: dict[str, str]) -> None:
    """Persist only the entries that differ from the built-in default."""
    overrides = {
        action_id: key_sequence
        for action_id, key_sequence in mapping.items()
        if action_id in DEFAULT_SHORTCUTS and key_sequence != DEFAULT_SHORTCUTS[action_id]
    }
    get_settings().setValue(SETTINGS_KEY_CUSTOM_SHORTCUTS, overrides)


def reset_shortcuts() -> dict[str, str]:
    """Clear all overrides and return the (now all-default) mapping."""
    get_settings().setValue(SETTINGS_KEY_CUSTOM_SHORTCUTS, {})
    return dict(DEFAULT_SHORTCUTS)


def normalize_key_sequence(text: str) -> str:
    """Round-trip `text` through QKeySequence so equivalent shortcuts typed
    differently (e.g. 'ctrl+n' vs 'Ctrl+N') compare as equal for duplicate
    detection. Returns "" for an empty/unassigned shortcut."""
    text = (text or "").strip()
    if not text:
        return ""
    return QKeySequence(text).toString(QKeySequence.SequenceFormat.PortableText)


def find_duplicates(mapping: dict[str, str]) -> dict[str, list[str]]:
    """Return {key_sequence: [action_id, ...]} for every non-empty key
    sequence assigned to more than one action -- used to block Save in the
    Shortcuts dialog until every conflict is resolved."""
    by_key: dict[str, list[str]] = {}
    for action_id, key_sequence in mapping.items():
        normalized = normalize_key_sequence(key_sequence)
        if not normalized:
            continue
        by_key.setdefault(normalized, []).append(action_id)
    return {key: ids for key, ids in by_key.items() if len(ids) > 1}
