"""
shortcuts_dialog.py
====================
Tools -> Keyboard Shortcuts... lets the user remap every customisable
action to a key sequence of their choice. Duplicate assignments are
flagged live and block Save until resolved; "Reset to Defaults" restores
the built-in shortcuts shipped with the app.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import make_scrollable
from app.utilities.constants import DEFAULT_SHORTCUTS, SHORTCUT_LABELS
from app.utilities.shortcuts import find_duplicates, get_shortcuts, normalize_key_sequence


class ShortcutsDialog(QDialog):
    """On accept(), call `result_mapping()` to get {action_id: key_sequence}."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(460, 480)

        outer_layout = QVBoxLayout(self)

        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: #e03131; font-weight: 600;")
        self.conflict_label.setWordWrap(True)
        self.conflict_label.setVisible(False)
        outer_layout.addWidget(self.conflict_label)

        content = QWidget()
        form = QFormLayout(content)
        form.setSpacing(8)

        self._edits: dict[str, QKeySequenceEdit] = {}
        current = get_shortcuts()
        for action_id, label in SHORTCUT_LABELS.items():
            edit = QKeySequenceEdit()
            edit.setKeySequence(current.get(action_id, DEFAULT_SHORTCUTS.get(action_id, "")))
            edit.keySequenceChanged.connect(self._revalidate)
            self._edits[action_id] = edit
            form.addRow(f"{label}:", edit)

        outer_layout.addWidget(make_scrollable(content), 1)

        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self._reset_to_defaults)
        outer_layout.addWidget(reset_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

        self._revalidate()

    # ------------------------------------------------------------------
    def _current_mapping(self) -> dict[str, str]:
        return {
            action_id: edit.keySequence().toString()
            for action_id, edit in self._edits.items()
        }

    def _revalidate(self, *_args) -> None:
        duplicates = find_duplicates(self._current_mapping())
        if duplicates:
            lines = []
            for key_sequence, action_ids in duplicates.items():
                names = ", ".join(SHORTCUT_LABELS.get(a, a) for a in action_ids)
                lines.append(f"'{key_sequence}' is assigned to: {names}")
            self.conflict_label.setText(
                "Duplicate shortcuts must be resolved before saving:\n" + "\n".join(lines)
            )
            self.conflict_label.setVisible(True)
            self.ok_button.setEnabled(False)
        else:
            self.conflict_label.setVisible(False)
            self.ok_button.setEnabled(True)

    def _reset_to_defaults(self) -> None:
        for action_id, edit in self._edits.items():
            edit.setKeySequence(DEFAULT_SHORTCUTS.get(action_id, ""))
        self._revalidate()

    def _on_accept(self) -> None:
        duplicates = find_duplicates(self._current_mapping())
        if duplicates:
            QMessageBox.warning(
                self, "Duplicate Shortcuts",
                "Please resolve the duplicate shortcut assignments shown above before saving.",
            )
            return
        self.accept()

    def result_mapping(self) -> dict[str, str]:
        """Normalized {action_id: key_sequence_string}, empty string = unassigned."""
        return {
            action_id: normalize_key_sequence(edit.keySequence().toString())
            for action_id, edit in self._edits.items()
        }
