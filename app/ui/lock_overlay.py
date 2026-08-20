"""
lock_overlay.py
================
Full-window "Interface Locked" overlay used by MainWindow's Tools ->
Full Lock action (Ctrl+Shift+L, under Tools -> Lock Interface). While shown it sits on top of the
entire central widget/docks and is the only interactive surface in the
window, so a locked bench PC can be left running mid-batch without a
passer-by being able to touch device settings, firmware, or the Upload/
Cancel buttons underneath it.

Unlocking requires typing the same special key (a passphrase, hashed with
SHA-256 and stored via AppSettings -- see MainWindow._on_lock_interface /
_on_unlock_interface) that was set when the interface was first locked.
This module only renders the prompt and emits what was typed; it never
sees or stores the real key itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LockOverlay(QWidget):
    """Opaque overlay that blocks the window and asks for the unlock key."""

    unlock_attempted = Signal(str)  # emits the text the user typed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("lockOverlay")
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "#lockOverlay { background-color: rgba(15, 16, 18, 235); }"
            "#lockOverlayCard { background-color: #26272b; border: 1px solid #3a3c42; "
            "border-radius: 10px; }"
            "#lockOverlayTitle { font-size: 20px; font-weight: 600; color: #e6e6e6; }"
            "#lockOverlaySubtitle { color: #9a9ea8; }"
        )
        # Grab all keyboard/mouse input so nothing underneath is reachable.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget(self)
        card.setObjectName("lockOverlayCard")
        card.setFixedWidth(360)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(12)

        title = QLabel("Interface Locked")
        title.setObjectName("lockOverlayTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        subtitle = QLabel("Enter the unlock key to resume.")
        subtitle.setObjectName("lockOverlaySubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        card_layout.addWidget(subtitle)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Unlock key")
        self.key_input.returnPressed.connect(self._emit_attempt)
        card_layout.addWidget(self.key_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e03131;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        unlock_button = QPushButton("Unlock")
        unlock_button.clicked.connect(self._emit_attempt)
        card_layout.addWidget(unlock_button)

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)

    def _emit_attempt(self) -> None:
        self.unlock_attempted.emit(self.key_input.text())

    def show_error(self, message: str = "Incorrect key. Try again.") -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.key_input.clear()
        self.key_input.setFocus()

    def reset_and_show(self) -> None:
        self.key_input.clear()
        self.error_label.setVisible(False)
        self.show()
        self.raise_()
        self.key_input.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Swallow every key while locked (besides what QLineEdit itself
        # needs) so global shortcuts like Ctrl+Q can't close the app
        # or reach whatever's underneath the overlay.
        event.accept()
