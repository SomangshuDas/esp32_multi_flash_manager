"""
validator.py
=============
Pre-upload validation. Runs a battery of checks across the set of devices
that are about to be flashed and produces a structured ValidationReport
that the UI renders as a report dialog before allowing the upload to
proceed. Nothing here touches hardware — it is a pure, fast, offline
sanity check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.device_manager.port_scanner import get_port_device_names
from app.models.device_model import DeviceConfig
from app.utilities.constants import SUPPORTED_CHIPS, FLASH_MODES
from app.utilities.helpers import is_valid_hex_address


class Severity(Enum):
    ERROR = "Error"
    WARNING = "Warning"


@dataclass
class ValidationIssue:
    severity: Severity
    device_name: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    def add_error(self, device_name: str, message: str) -> None:
        self.issues.append(ValidationIssue(Severity.ERROR, device_name, message))

    def add_warning(self, device_name: str, message: str) -> None:
        self.issues.append(ValidationIssue(Severity.WARNING, device_name, message))


def validate_devices(
    devices: list[DeviceConfig],
    connected_ports: set[str] | None = None,
    monitor_ports: set[str] | None = None,
) -> ValidationReport:
    """
    Validate a list of devices that are about to be flashed together.
    Returns a ValidationReport containing every issue found; the caller
    decides whether ERROR-level issues block the upload (they should).

    `connected_ports` is the set of serial ports currently visible to the
    OS (e.g. from PortWatcher's live scan). If omitted, a fresh scan is
    taken here so this function still works standalone/in tests. Passing
    it in lets the caller flag "port not connected" immediately when
    Upload is clicked, instead of only finding out ~10-30 seconds later
    when esptool's own connect-retry loop finally gives up.

    `monitor_ports` is the set of serial ports that currently have a
    connected Serial Monitor window open (see app/ui/serial_monitor.py).
    esptool cannot open a port that's already held open elsewhere, so any
    device whose port is in this set is flagged as an error telling the
    user to close that Serial Monitor before uploading.
    """
    report = ValidationReport()
    if connected_ports is None:
        connected_ports = get_port_device_names()
    if monitor_ports is None:
        monitor_ports = set()

    # --- Duplicate port detection (only across devices being uploaded) ---
    port_usage: dict[str, list[str]] = {}
    for device in devices:
        if device.com_port:
            port_usage.setdefault(device.com_port, []).append(device.name)
    for port, names in port_usage.items():
        if len(names) > 1:
            for name in names:
                report.add_error(name, f"Port {port} is used by multiple devices: {', '.join(names)}")

    for device in devices:
        _validate_single_device(device, report, connected_ports, monitor_ports)

    return report


def _validate_single_device(
    device: DeviceConfig,
    report: ValidationReport,
    connected_ports: set[str],
    monitor_ports: set[str],
) -> None:
    name = device.name

    if not device.com_port:
        report.add_error(name, "No port selected.")
    elif device.com_port not in connected_ports:
        report.add_error(
            name,
            f"Port {device.com_port} is not currently connected. Plug in the device, or "
            "select the correct port in Device Settings, then try again.",
        )
    elif device.com_port in monitor_ports:
        report.add_error(
            name,
            f"A Serial Monitor is currently open on port {device.com_port}. Close it before uploading.",
        )

    if device.chip_type not in SUPPORTED_CHIPS:
        report.add_error(name, f"Unsupported/invalid chip selection: '{device.chip_type}'.")

    if device.flash_mode not in FLASH_MODES:
        report.add_error(name, f"Invalid flash mode: '{device.flash_mode}'.")

    enabled = device.enabled_firmware()
    if not enabled:
        report.add_error(name, "No enabled firmware files to flash.")
        return

    # Missing bootloader / partition table heuristic warnings (only relevant
    # for full-image flashing at address 0x1000 / 0x8000 conventions).
    addresses = {e.address.lower() for e in enabled}
    has_low_address_image = any(
        is_valid_hex_address(a) and int(a, 16) < 0x9000 for a in addresses
    )
    if has_low_address_image:
        if "0x1000" not in addresses:
            report.add_warning(name, "No firmware assigned to 0x1000 (bootloader) — this may be intentional if flashing a merged image.")
        if "0x8000" not in addresses:
            report.add_warning(name, "No firmware assigned to 0x8000 (partition table) — this may be intentional if flashing a merged image.")

    # Per-file checks: missing files, invalid/duplicate addresses.
    seen_addresses: dict[str, str] = {}
    for entry in enabled:
        if not entry.file_path:
            report.add_error(name, "A firmware row has no file selected.")
            continue
        if entry.missing:
            report.add_error(name, f"Firmware file missing on disk: {entry.file_path}")
        if not is_valid_hex_address(entry.address):
            report.add_error(name, f"Invalid flash address '{entry.address}' for {entry.file_name}.")
            continue
        norm = entry.address.lower()
        if norm in seen_addresses:
            report.add_error(
                name,
                f"Duplicate flash address {entry.address} used by both "
                f"'{seen_addresses[norm]}' and '{entry.file_name}'.",
            )
        else:
            seen_addresses[norm] = entry.file_name
