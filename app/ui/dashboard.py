"""
dashboard.py
============
A compact stats bar shown at the top of the main window, giving an
at-a-glance summary of the whole fleet: total devices, how many are
currently connected, ready, uploading, failed, and completed.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.models.device_model import DeviceConfig
from app.utilities.constants import (
    ACTIVE_STATUSES,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_WAITING,
)


class _StatTile(QFrame):
    def __init__(self, title: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statTile")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color};")
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 11px; color: #9a9ca3;")

        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def set_value(self, value: int) -> None:
        self.value_label.setText(str(value))


class DashboardWidget(QWidget):
    """Horizontal row of stat tiles. Call refresh(devices) whenever anything changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.tile_total = _StatTile("Total Devices", "#e6e6e6")
        self.tile_connected = _StatTile("Connected", "#2f9e44")
        self.tile_disconnected = _StatTile("Disconnected", "#e03131")
        self.tile_ready = _StatTile("Ready", "#5b8def")
        self.tile_uploading = _StatTile("Uploading", "#e0a300")
        self.tile_failed = _StatTile("Failed", "#e03131")
        self.tile_completed = _StatTile("Completed", "#2f9e44")

        for tile in (
            self.tile_total, self.tile_connected, self.tile_disconnected,
            self.tile_ready, self.tile_uploading, self.tile_failed, self.tile_completed,
        ):
            layout.addWidget(tile)
        layout.addStretch(1)

    def refresh(self, devices: list[DeviceConfig], connected_ports: set[str]) -> None:
        total = len(devices)
        connected = sum(1 for d in devices if d.com_port in connected_ports)
        disconnected = total - connected
        ready = sum(1 for d in devices if d.runtime.status == STATUS_WAITING)
        uploading = sum(1 for d in devices if d.runtime.status in ACTIVE_STATUSES)
        failed = sum(1 for d in devices if d.runtime.status == STATUS_FAILED)
        completed = sum(1 for d in devices if d.runtime.status == STATUS_COMPLETED)

        self.tile_total.set_value(total)
        self.tile_connected.set_value(connected)
        self.tile_disconnected.set_value(disconnected)
        self.tile_ready.set_value(ready)
        self.tile_uploading.set_value(uploading)
        self.tile_failed.set_value(failed)
        self.tile_completed.set_value(completed)
