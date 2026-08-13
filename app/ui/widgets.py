"""
widgets.py
==========
Small, reusable custom widgets shared by multiple panels.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QScrollArea, QTableWidget, QWidget

from app.utilities.constants import STATUS_COLORS


def fit_table_columns(table: QTableWidget, min_widths: dict[int, int] | None = None) -> None:
    """Grow every column to fit its current header + cell content (never
    shrink below that) instead of letting Qt silently elide/truncate cell
    text to whatever width a column happens to have. Once the sum of the
    column widths exceeds the viewport, the table's own horizontal
    scrollbar takes over - nothing is ever clipped.
    """
    table.resizeColumnsToContents()
    if min_widths:
        for column, min_width in min_widths.items():
            if table.columnWidth(column) < min_width:
                table.setColumnWidth(column, min_width)


def prepare_table_for_full_content(table: QTableWidget) -> None:
    """One-time setup so a table's columns can freely grow to fit content
    (see fit_table_columns) and, if that ends up wider than the viewport,
    both scrollbars appear rather than the table compressing columns.
    """
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    for column in range(table.columnCount()):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)


def make_scrollable(content: QWidget, *, horizontal: bool = True, vertical: bool = True) -> QScrollArea:
    """Wrap `content` in a QScrollArea so its horizontal and/or vertical
    scrollbar appears automatically whenever the content's natural size
    exceeds whatever space the parent layout ends up giving it (a small
    dialog, a dragged-thin splitter panel, a resized dock, etc.). Nothing
    is ever silently clipped or hidden.
    """
    scroll = QScrollArea()
    scroll.setWidget(content)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded if horizontal else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    scroll.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded if vertical else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    return scroll


class StatusBadge(QWidget):
    """A small colored dot + text label reflecting a device's current status."""

    def __init__(self, status: str = "Waiting", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # As a table cell widget (rather than a QTableWidgetItem) this badge
        # is a real child widget composited on top of the row, so it never
        # picks up the view's item:selected/alternate-row background on its
        # own. The global QWidget {} rule would otherwise paint it as a
        # solid opaque box that doesn't turn blue with the rest of a
        # selected row - so it and its labels are forced transparent here,
        # letting whatever the row is actually painted with show through.
        self.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._text = QLabel()
        self._text.setStyleSheet("background-color: transparent;")

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
