"""
Unit tests for app/controllers/undo_stack.py -- pure Python, no Qt
dependency, so these run without qtbot.
"""

from __future__ import annotations

from app.controllers.undo_stack import UndoStack
from app.models.device_model import DeviceConfig


def _devices(*names: str) -> list[DeviceConfig]:
    return [DeviceConfig(name=n) for n in names]


class TestPushAndUndo:
    def test_fresh_stack_cannot_undo_or_redo(self):
        stack = UndoStack()
        assert not stack.can_undo()
        assert not stack.can_redo()
        assert stack.undo() is None
        assert stack.redo() is None

    def test_push_enables_undo_not_redo(self):
        stack = UndoStack()
        stack.push("edit", _devices("A"), _devices("B"))
        assert stack.can_undo()
        assert not stack.can_redo()

    def test_undo_returns_before_snapshot(self):
        stack = UndoStack()
        before = _devices("A")
        after = _devices("B")
        stack.push("rename", before, after)
        result = stack.undo()
        assert [d.name for d in result] == ["A"]

    def test_undo_moves_entry_to_redo_stack(self):
        stack = UndoStack()
        stack.push("edit", _devices("A"), _devices("B"))
        stack.undo()
        assert not stack.can_undo()
        assert stack.can_redo()

    def test_redo_returns_after_snapshot(self):
        stack = UndoStack()
        stack.push("rename", _devices("A"), _devices("B"))
        stack.undo()
        result = stack.redo()
        assert [d.name for d in result] == ["B"]

    def test_redo_moves_entry_back_to_undo_stack(self):
        stack = UndoStack()
        stack.push("edit", _devices("A"), _devices("B"))
        stack.undo()
        stack.redo()
        assert stack.can_undo()
        assert not stack.can_redo()

    def test_new_push_clears_redo_stack(self):
        stack = UndoStack()
        stack.push("edit1", _devices("A"), _devices("B"))
        stack.undo()
        assert stack.can_redo()
        stack.push("edit2", _devices("B"), _devices("C"))
        assert not stack.can_redo()

    def test_undo_then_redo_round_trip_preserves_state(self):
        stack = UndoStack()
        before = _devices("A", "B")
        after = _devices("A", "B-renamed")
        stack.push("rename", before, after)
        undone = stack.undo()
        assert [d.name for d in undone] == ["A", "B"]
        redone = stack.redo()
        assert [d.name for d in redone] == ["A", "B-renamed"]


class TestSnapshotIndependence:
    def test_returned_snapshot_is_a_deep_copy_not_a_live_reference(self):
        stack = UndoStack()
        before = _devices("A")
        stack.push("edit", before, _devices("B"))
        snapshot = stack.undo()
        snapshot[0].name = "mutated"
        # Mutating the returned snapshot must never corrupt the stack's
        # own stored copy -- undoing again should still see "A".
        stack.push("edit2", _devices("mutated"), _devices("C"))
        stack.undo()
        redo_snapshot = stack.redo()
        assert redo_snapshot[0].name == "C"

    def test_push_deep_copies_the_input_lists_too(self):
        stack = UndoStack()
        before = _devices("A")
        stack.push("edit", before, _devices("B"))
        before[0].name = "mutated-after-push"
        undone = stack.undo()
        assert undone[0].name == "A"


class TestDescriptions:
    def test_undo_description_reflects_top_of_stack(self):
        stack = UndoStack()
        stack.push("first op", _devices("A"), _devices("B"))
        stack.push("second op", _devices("B"), _devices("C"))
        assert stack.undo_description() == "second op"

    def test_undo_description_none_when_empty(self):
        stack = UndoStack()
        assert stack.undo_description() is None

    def test_redo_description_after_undo(self):
        stack = UndoStack()
        stack.push("first op", _devices("A"), _devices("B"))
        stack.undo()
        assert stack.redo_description() == "first op"


class TestMaxDepth:
    def test_stack_trims_oldest_entries_beyond_max_depth(self):
        stack = UndoStack(max_depth=2)
        stack.push("op1", _devices("A"), _devices("B"))
        stack.push("op2", _devices("B"), _devices("C"))
        stack.push("op3", _devices("C"), _devices("D"))
        # op1 should have been trimmed -- only 2 undo steps available.
        assert stack.undo_description() == "op3"
        stack.undo()
        assert stack.undo_description() == "op2"
        stack.undo()
        assert not stack.can_undo()

    def test_set_max_depth_trims_existing_entries(self):
        stack = UndoStack(max_depth=5)
        for i in range(5):
            stack.push(f"op{i}", _devices("A"), _devices("B"))
        stack.set_max_depth(2)
        count = 0
        while stack.can_undo():
            stack.undo()
            count += 1
        assert count == 2

    def test_max_depth_is_clamped_to_at_least_one(self):
        stack = UndoStack(max_depth=0)
        assert stack.max_depth == 1


class TestClear:
    def test_clear_drops_both_stacks(self):
        stack = UndoStack()
        stack.push("edit", _devices("A"), _devices("B"))
        stack.undo()
        assert stack.can_redo()
        stack.clear()
        assert not stack.can_undo()
        assert not stack.can_redo()
