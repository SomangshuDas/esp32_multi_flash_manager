"""
undo_stack.py
=============
Whole-device-list snapshot undo/redo stack backing DeviceController's four
bulk mutation operations: Batch Edit, bulk device removal, Assign Firmware
Set to Devices, and CSV import (see ROADMAP.md's "Undo/redo for mutating
operations" entry for the original design rationale).

Design choice: operate on whole-device-list snapshots rather than a
field-level diff/patch system. DeviceConfig (and everything it contains --
FirmwareEntry, SecurityConfig) is a plain, cheap-to-deep-copy dataclass, so
snapshotting the entire project device list before/after each operation is
much simpler to implement correctly than a generic diff/patch engine, at
the cost of somewhat more memory per undo step -- acceptable given
realistic device-list sizes (see MAX_DEVICES_PER_PROJECT in
docs/THREAT_MODEL.md). The stack depth is bounded (see
SETTINGS_KEY_UNDO_STACK_DEPTH / get_undo_stack_depth()) precisely to keep
that memory cost under user control.

This module has no Qt dependency and no knowledge of DeviceController or
ProjectModel beyond "a list of DeviceConfig" -- it is pure bookkeeping, so
it's trivially unit-testable on its own.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.device_model import DeviceConfig


@dataclass
class UndoEntry:
    """One undoable operation. `before`/`after` are the FULL project
    device list at the moment the operation was pushed (already
    deep-copied by UndoStack.push -- callers do not need to copy their
    own snapshots first)."""

    description: str
    before: "list[DeviceConfig]" = field(default_factory=list)
    after: "list[DeviceConfig]" = field(default_factory=list)


class UndoStack:
    """Bounded undo/redo stack of UndoEntry snapshots.

    Usage from DeviceController:
        before = copy of project.devices taken BEFORE the mutation
        ... mutate project.devices ...
        after = copy of project.devices taken AFTER the mutation
        undo_stack.push("Batch Edit: baud_rate", before, after)

    undo()/redo() each return a fresh, independent device-list snapshot
    ready to swap directly into ProjectModel.devices -- further mutation
    of the returned list never corrupts the stack's own stored copies.
    """

    def __init__(self, max_depth: int = 25) -> None:
        self.max_depth = max(1, max_depth)
        self._undo: list[UndoEntry] = []
        self._redo: list[UndoEntry] = []

    # ------------------------------------------------------------------
    def push(
        self, description: str, before: "list[DeviceConfig]", after: "list[DeviceConfig]",
    ) -> None:
        """Record one undoable operation. Pushing always clears the redo
        stack (standard undo/redo semantics -- a new action invalidates
        any previously-undone future)."""
        entry = UndoEntry(
            description=description,
            before=copy.deepcopy(before),
            after=copy.deepcopy(after),
        )
        self._undo.append(entry)
        while len(self._undo) > self.max_depth:
            self._undo.pop(0)
        self._redo.clear()

    def set_max_depth(self, max_depth: int) -> None:
        """Update the depth cap (e.g. live after a Settings change) and
        immediately trim any excess older entries."""
        self.max_depth = max(1, max_depth)
        while len(self._undo) > self.max_depth:
            self._undo.pop(0)

    # ------------------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_description(self) -> str | None:
        return self._undo[-1].description if self._undo else None

    def redo_description(self) -> str | None:
        return self._redo[-1].description if self._redo else None

    # ------------------------------------------------------------------
    def undo(self) -> "list[DeviceConfig] | None":
        """Pop the most recent operation, move it to the redo stack, and
        return the device-list snapshot to restore (the state BEFORE that
        operation ran). Returns None if there is nothing to undo."""
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return copy.deepcopy(entry.before)

    def redo(self) -> "list[DeviceConfig] | None":
        """Pop the most recently undone operation, move it back to the
        undo stack, and return the device-list snapshot to restore (the
        state AFTER that operation ran). Returns None if there is
        nothing to redo."""
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return copy.deepcopy(entry.after)

    def clear(self) -> None:
        """Drop all history (e.g. when a new/different project is loaded --
        undoing across a project swap makes no sense)."""
        self._undo.clear()
        self._redo.clear()
