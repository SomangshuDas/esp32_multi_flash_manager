"""
port_scanner.py
================
Wraps pyserial's list_ports to provide live serial port discovery, including
VID/PID and a best-effort chip guess based on common USB-serial bridge
identifiers used on ESP32 dev boards (CP210x, CH340, FTDI).

This module is deliberately free of Qt imports so it can be unit-tested
or reused headlessly; PortWatcher (in app/workers) wraps this in a QTimer
loop for the live UI.
"""

from __future__ import annotations

from dataclasses import dataclass

import serial.tools.list_ports as list_ports

from app.logging_setup.logger import get_logger

logger = get_logger(__name__)

# Well-known USB VID:PID pairs for common ESP32 USB-serial bridges.
_KNOWN_BRIDGES = {
    (0x10C4, 0xEA60): "Silicon Labs CP210x",
    (0x1A86, 0x7523): "CH340",
    (0x1A86, 0x55D4): "CH9102 (CH343)",
    (0x0403, 0x6001): "FTDI FT232R",
    (0x303A, 0x1001): "Espressif Native USB (S2/S3/C3)",
}


@dataclass(frozen=True)
class PortInfo:
    device: str          # e.g. "COM5" on Windows, "/dev/ttyUSB0" on Linux,
                         # "/dev/cu.usbserial-0001" on macOS
    description: str
    vid: int | None
    pid: int | None
    serial_number: str | None

    @property
    def vid_pid_str(self) -> str:
        if self.vid is None or self.pid is None:
            return "-"
        return f"{self.vid:04X}:{self.pid:04X}"

    @property
    def bridge_name(self) -> str:
        if self.vid is None or self.pid is None:
            return "Unknown"
        return _KNOWN_BRIDGES.get((self.vid, self.pid), "Generic USB-Serial")


def list_available_ports() -> list[PortInfo]:
    """Return every serial port currently visible to the OS."""
    ports: list[PortInfo] = []
    try:
        for port in list_ports.comports():
            ports.append(
                PortInfo(
                    device=port.device,
                    description=port.description or "",
                    vid=port.vid,
                    pid=port.pid,
                    serial_number=port.serial_number,
                )
            )
    except Exception:  # noqa: BLE001 - never let a scan crash the app
        logger.exception("Failed to enumerate serial ports")
    return ports


def get_port_device_names() -> set[str]:
    """Return just the set of device name strings, e.g. {'COM3', 'COM5'} on
    Windows or {'/dev/ttyUSB0', '/dev/ttyUSB1'} on Linux."""
    return {p.device for p in list_available_ports()}
