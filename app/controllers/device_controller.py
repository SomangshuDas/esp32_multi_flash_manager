"""
device_controller.py
=====================
Mediates between the ProjectModel's device list and the UI. Owns no
widgets directly (MVC discipline) — it exposes Qt signals that
DevicePanel and other views subscribe to, and plain methods that views
call in response to user actions.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.models.project_model import ProjectModel
from app.utilities.app_settings import get_settings
from app.utilities.constants import DEFAULT_BAUD, DEFAULT_FLASH_MODE

logger = get_logger(__name__)


class DeviceController(QObject):
    """
    Signals
    -------
    device_added(str)          - device_id
    device_removed(str)        - device_id
    device_updated(str)        - device_id (config changed, not runtime status)
    devices_reset()            - the whole list was replaced (e.g. project load)
    """

    device_added = Signal(str)
    device_removed = Signal(str)
    device_updated = Signal(str)
    devices_reset = Signal()

    def __init__(self, project: ProjectModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.project = project

    # ------------------------------------------------------------------
    def set_project(self, project: ProjectModel) -> None:
        """Swap in a whole new project (used after loading a project file)."""
        self.project = project
        self.devices_reset.emit()

    def devices(self) -> list[DeviceConfig]:
        return self.project.devices

    def get_device(self, device_id: str) -> DeviceConfig | None:
        return self.project.find_device(device_id)

    # ------------------------------------------------------------------
    def add_device(self, name: str = "New Device") -> DeviceConfig:
        # New devices pick up the app-wide "Default Baud Rate" / "Default
        # Flash Mode" from Settings (falling back to the constants module
        # if the user has never opened Settings yet), so changing those
        # preferences actually applies to devices added afterwards instead
        # of only affecting the Settings dialog itself.
        settings = get_settings()
        device = DeviceConfig(
            name=name,
            baud_rate=int(settings.value("default_baud", DEFAULT_BAUD)),
            flash_mode=str(settings.value("default_flash_mode", DEFAULT_FLASH_MODE)),
        )
        self.project.add_device(device)
        logger.info("Added device '%s' (%s)", device.name, device.id)
        self.device_added.emit(device.id)
        return device

    def remove_device(self, device_id: str) -> None:
        device = self.get_device(device_id)
        if device is None:
            return
        self.project.remove_device(device_id)
        logger.info("Removed device '%s' (%s)", device.name, device_id)
        self.device_removed.emit(device_id)

    def duplicate_device(self, device_id: str) -> DeviceConfig | None:
        source = self.get_device(device_id)
        if source is None:
            return None
        clone = source.clone()
        self.project.add_device(clone)
        logger.info("Duplicated device '%s' -> '%s'", source.name, clone.name)
        self.device_added.emit(clone.id)
        return clone

    def notify_updated(self, device_id: str) -> None:
        """Call after mutating a device's fields directly (e.g. from a dialog)."""
        self.device_updated.emit(device_id)

    # ------------------------------------------------------------------
    def apply_to_all(self, predicate_field: str, value) -> None:
        """
        Batch-edit helper: set `predicate_field` to `value` on every device
        in the project, then emit device_updated for each. Used by the
        Batch Editing dialog (e.g. set baud_rate=115200 for all devices).
        """
        for device in self.project.devices:
            if hasattr(device, predicate_field):
                setattr(device, predicate_field, value)
                self.device_updated.emit(device.id)
        logger.info("Batch-applied %s=%s to %d device(s)", predicate_field, value, len(self.project.devices))

    def apply_to_selected(self, device_ids: list[str], predicate_field: str, value) -> None:
        for device_id in device_ids:
            device = self.get_device(device_id)
            if device is not None and hasattr(device, predicate_field):
                setattr(device, predicate_field, value)
                self.device_updated.emit(device.id)
        logger.info("Batch-applied %s=%s to %d selected device(s)", predicate_field, value, len(device_ids))

    def apply_firmware_to_devices(self, device_ids: list[str], entries: list) -> int:
        """
        Factory Batch Flash helper: replace `device_ids`' firmware lists
        with independent copies of the same `entries` (as produced by
        `scan_firmware_folder()`), so one imported "firmware set" can be
        stamped onto many devices in one step instead of re-importing per
        device. Each device gets its own `FirmwareEntry.duplicate()`s
        (fresh ids) so editing one device's addresses later never mutates
        another device's copy. Returns the number of devices updated.
        """
        updated = 0
        for device_id in device_ids:
            device = self.get_device(device_id)
            if device is None:
                continue
            device.firmware = [entry.duplicate() for entry in entries]
            self.device_updated.emit(device.id)
            updated += 1
        logger.info("Applied firmware set (%d file(s)) to %d device(s)", len(entries), updated)
        return updated

    # ------------------------------------------------------------------
    def find_duplicate_ports(self) -> dict[str, list[str]]:
        """Return {com_port: [device names]} for every port used more than once."""
        usage: dict[str, list[str]] = {}
        for device in self.project.devices:
            if device.com_port:
                usage.setdefault(device.com_port, []).append(device.name)
        return {port: names for port, names in usage.items() if len(names) > 1}

    def search(self, query: str) -> list[DeviceConfig]:
        """Filter devices by name / port / chip / current status (case-insensitive)."""
        if not query.strip():
            return self.project.devices
        query = query.lower()
        return [
            d for d in self.project.devices
            if query in d.name.lower()
            or query in d.com_port.lower()
            or query in d.chip_type.lower()
            or query in d.runtime.status.lower()
        ]
