"""
widgets.py
==========
Small, reusable custom widgets shared by multiple panels.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.utilities.constants import STATUS_COLORS


class StatusBadge(QWidget):
    """A small colored dot + text label reflecting a device's current status."""

    def __init__(self, status: str = "Waiting", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._text = QLabel()

        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        layout.addStretch(1)

        self.set_status(status)

    def set_status(self, status: str) -> None:
        color = STATUS_COLORS.get(status, "#8a8f98")
        self._dot.setStyleSheet(
            f"background-color: {color}; border-radius: 5px;"
        )
        self._text.setText(status)


class ColorSwatch(QLabel):
    """A tiny rectangle of solid color; used in legends and dashboard tiles."""

    def __init__(self, hex_color: str, size: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setStyleSheet(f"background-color: {hex_color}; border-radius: 3px;")


def status_qcolor(status: str) -> QColor:
    return QColor(STATUS_COLORS.get(status, "#8a8f98"))
