"""
port_watcher.py
================
Polls the OS for available serial ports on a QTimer and emits Qt signals
whenever the set of ports changes, so the UI can flag devices whose COM
port was unplugged (or celebrate a reconnect) in near-real-time without
blocking the GUI thread. Polling (rather than OS-level USB hotplug
events) is used deliberately for cross-platform simplicity and reliability
inside a Qt event loop.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from app.device_manager.port_scanner import PortInfo, list_available_ports
from app.logging_setup.logger import get_logger
from app.utilities.constants import PORT_SCAN_INTERVAL_MS

logger = get_logger(__name__)


class PortWatcher(QObject):
    """
    Signals
    -------
    ports_changed(list[PortInfo])   - emitted on every poll with the full list
    port_connected(str)             - a new serial port name appeared
    port_disconnected(str)          - a previously seen serial port name vanished
    """

    ports_changed = Signal(list)
    port_connected = Signal(str)
    port_disconnected = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(PORT_SCAN_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._known_ports: set[str] = set()

    def start(self) -> None:
        self._poll()  # immediate first scan so the UI isn't empty on launch
        self._timer.start()
        logger.info("PortWatcher started (interval=%dms)", PORT_SCAN_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()

    def _poll(self) -> None:
        ports: list[PortInfo] = list_available_ports()
        current_names = {p.device for p in ports}

        newly_connected = current_names - self._known_ports
        newly_disconnected = self._known_ports - current_names

        for name in newly_connected:
            self.port_connected.emit(name)
        for name in newly_disconnected:
            self.port_disconnected.emit(name)

        self._known_ports = current_names
        self.ports_changed.emit(ports)
