"""
device_controller.py
=====================
Mediates between the ProjectModel's device list and the UI. Owns no
widgets directly (MVC discipline) — it exposes Qt signals that
DevicePanel and other views subscribe to, and plain methods that views
call in response to user actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.models.project_model import ProjectModel
from app.utilities.app_settings import get_default_device_profile_name, get_settings
from app.utilities.constants import DEFAULT_BAUD, DEFAULT_FLASH_MODE

if TYPE_CHECKING:
    from app.controllers.flash_controller import FlashController
    from app.project_manager.csv_import import CsvImportResult

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
        # Traceability bug fix: apply_to_all/apply_to_selected/
        # apply_firmware_to_devices used to mutate a DeviceConfig
        # regardless of whether FlashController.is_busy() was true for it.
        # Because FlashWorker holds a live reference to that same object,
        # renaming a device or reassigning its port mid-flash via Batch
        # Edit made the resulting history entry reflect the *new* values
        # rather than what was actually flashed. When a FlashController is
        # wired in (see set_flash_controller / main_window.py wiring),
        # the three batch-mutation methods below skip busy devices instead
        # of silently corrupting their in-flight history record.
        self._flash_controller: "FlashController | None" = None

    # ------------------------------------------------------------------
    def set_flash_controller(self, flash_controller: "FlashController") -> None:
        """Wire in the FlashController used to guard batch-mutation methods
        against editing a device that's currently mid-flash. See the
        docstring on __init__ for the bug this closes."""
        self._flash_controller = flash_controller

    def _is_device_busy(self, device_id: str) -> bool:
        return self._flash_controller is not None and self._flash_controller.is_busy(device_id)

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
        self._apply_default_profile(device)
        self.project.add_device(device)
        logger.info("Added device '%s' (%s)", device.name, device.id)
        self.device_added.emit(device.id)
        return device

    def _apply_default_profile(self, device: DeviceConfig) -> None:
        """If Settings -> General -> "Default Device Profile" names a saved
        Firmware Profile, overlay its chip/flash settings and firmware
        list onto `device` (Settings -> General). A missing/deleted
        profile name (e.g. the user deleted the profile after selecting
        it) is treated the same as "no default set" -- the device keeps
        its already-applied Default Baud Rate/Flash Mode instead of
        raising an error that would block adding a device entirely.
        """
        profile_name = get_default_device_profile_name()
        if not profile_name:
            return
        from app.firmware_manager.profiles import list_profiles

        for profile in list_profiles():
            if profile.name == profile_name:
                profile.apply_to_device(device)
                logger.info(
                    "Applied default device profile '%s' to new device '%s'", profile_name, device.name
                )
                return
        logger.warning(
            "Default device profile '%s' is configured but no longer exists; skipping", profile_name
        )

    def import_from_csv(self, csv_path: str) -> "CsvImportResult":
        """Bulk-import devices from a CSV file (Devices -> Import Devices
        from CSV...). Each successfully parsed row becomes a new device,
        appended to the project the same way add_device() would, and
        emits device_added for each one so the UI updates incrementally
        rather than needing a full refresh. Returns the CsvImportResult
        (imported devices + any per-row errors) so the caller can show a
        summary -- partial success (some rows imported, some skipped) is
        the common case for a real production CSV, not an edge case."""
        from app.project_manager.csv_import import import_devices_from_csv

        result = import_devices_from_csv(csv_path)
        for device in result.devices:
            self._apply_default_profile(device)
            self.project.add_device(device)
            self.device_added.emit(device.id)
        if result.devices:
            logger.info("Imported %d device(s) from CSV: %s", len(result.devices), csv_path)
        return result

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
        Devices currently mid-flash (FlashController.is_busy()) are
        skipped -- see __init__ docstring for why.
        """
        skipped = 0
        for device in self.project.devices:
            if self._is_device_busy(device.id):
                skipped += 1
                continue
            if hasattr(device, predicate_field):
                setattr(device, predicate_field, value)
                self.device_updated.emit(device.id)
        logger.info("Batch-applied %s=%s to %d device(s)", predicate_field, value, len(self.project.devices))
        if skipped:
            logger.warning(
                "Skipped %d device(s) mid-flash while batch-applying %s", skipped, predicate_field
            )

    def apply_to_selected(self, device_ids: list[str], predicate_field: str, value) -> None:
        skipped = 0
        for device_id in device_ids:
            if self._is_device_busy(device_id):
                skipped += 1
                continue
            device = self.get_device(device_id)
            if device is not None and hasattr(device, predicate_field):
                setattr(device, predicate_field, value)
                self.device_updated.emit(device.id)
        logger.info("Batch-applied %s=%s to %d selected device(s)", predicate_field, value, len(device_ids))
        if skipped:
            logger.warning(
                "Skipped %d selected device(s) mid-flash while batch-applying %s", skipped, predicate_field
            )

    def apply_firmware_to_devices(self, device_ids: list[str], entries: list) -> int:
        """
        Assign Firmware Set to Devices helper: replace `device_ids`'
        firmware lists with independent copies of the same `entries` (as
        produced by `scan_firmware_folder()`), so one imported "firmware
        set" can be stamped onto many devices (all of them, or just a
        selected subset) in one step instead of re-importing per device.
        Each device gets its own `FirmwareEntry.duplicate()`s (fresh ids)
        so editing one device's addresses later never mutates another
        device's copy. Returns the number of devices updated. Devices
        currently mid-flash (FlashController.is_busy()) are skipped -- see
        __init__ docstring for why.
        """
        updated = 0
        skipped = 0
        for device_id in device_ids:
            if self._is_device_busy(device_id):
                skipped += 1
                continue
            device = self.get_device(device_id)
            if device is None:
                continue
            device.firmware = [entry.duplicate() for entry in entries]
            self.device_updated.emit(device.id)
            updated += 1
        logger.info("Applied firmware set (%d file(s)) to %d device(s)", len(entries), updated)
        if skipped:
            logger.warning("Skipped %d device(s) mid-flash while applying firmware set", skipped)
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
        """Filter devices by name / port / chip / current status / tag (case-insensitive)."""
        if not query.strip():
            return self.project.devices
        query = query.lower()
        return [
            d for d in self.project.devices
            if query in d.name.lower()
            or query in d.com_port.lower()
            or query in d.chip_type.lower()
            or query in d.runtime.status.lower()
            or any(query in tag.lower() for tag in d.tags)
        ]

    def all_tags(self) -> list[str]:
        """Sorted list of every distinct tag currently used by any device."""
        tags: set[str] = set()
        for device in self.project.devices:
            tags.update(device.tags)
        return sorted(tags, key=str.lower)

    def add_tag_to_devices(self, device_ids: list[str], tag: str) -> int:
        """Add `tag` to each device in `device_ids` (no duplicates). Returns
        the number of devices updated. Used by Batch Edit's 'Tags (Add)'
        field, which appends rather than overwriting like other fields."""
        tag = tag.strip()
        if not tag:
            return 0
        updated = 0
        for device_id in device_ids:
            device = self.get_device(device_id)
            if device is None:
                continue
            if tag not in device.tags:
                device.tags.append(tag)
            self.device_updated.emit(device.id)
            updated += 1
        logger.info("Batch-added tag '%s' to %d device(s)", tag, updated)
        return updated
