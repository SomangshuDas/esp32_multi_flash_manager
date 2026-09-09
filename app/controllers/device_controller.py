"""
device_controller.py
=====================
Mediates between the ProjectModel's device list and the UI. Owns no
widgets directly (MVC discipline) — it exposes Qt signals that
DevicePanel and other views subscribe to, and plain methods that views
call in response to user actions.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from app.controllers.undo_stack import UndoStack
from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.models.project_model import ProjectModel
from app.utilities.app_settings import get_default_device_profile_name, get_settings, get_undo_stack_depth
from app.utilities.constants import DEFAULT_BAUD, DEFAULT_FLASH_MODE

if TYPE_CHECKING:
    from app.controllers.flash_controller import FlashController
    from app.project_manager.csv_import import CsvImportResult
    from app.project_manager.zip_manifest_import import ZipManifestImportResult

logger = get_logger(__name__)


class DeviceController(QObject):
    """
    Signals
    -------
    device_added(str)          - device_id
    device_removed(str)        - device_id
    device_updated(str)        - device_id (config changed, not runtime status)
    devices_reset()            - the whole list was replaced (e.g. project load,
                                  bulk removal, or an undo()/redo())
    undo_stack_changed()       - can_undo()/can_redo() availability changed;
                                  the UI (Edit menu / shortcuts) should refresh
    """

    device_added = Signal(str)
    device_removed = Signal(str)
    device_updated = Signal(str)
    devices_reset = Signal()
    undo_stack_changed = Signal()

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
        # See app/controllers/undo_stack.py's module docstring for the
        # whole-snapshot design rationale. Depth is read from Settings ->
        # Advanced -> "Undo History Depth" (see
        # app.utilities.app_settings.get_undo_stack_depth) at construction
        # time; call refresh_undo_stack_depth() after a Settings change to
        # pick up a new value live without restarting.
        self.undo_stack = UndoStack(max_depth=get_undo_stack_depth())

    def refresh_undo_stack_depth(self) -> None:
        """Re-read Settings -> Advanced -> "Undo History Depth" and apply
        it to the live undo stack immediately (called after Settings is
        closed with changes saved)."""
        self.undo_stack.set_max_depth(get_undo_stack_depth())

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
        # Undo history from the previous project makes no sense once its
        # device list has been replaced entirely.
        self.undo_stack.clear()
        self.undo_stack_changed.emit()
        self.devices_reset.emit()

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------
    def _snapshot(self) -> list[DeviceConfig]:
        return copy.deepcopy(self.project.devices)

    def can_undo(self) -> bool:
        return self.undo_stack.can_undo()

    def can_redo(self) -> bool:
        return self.undo_stack.can_redo()

    def undo_description(self) -> str | None:
        return self.undo_stack.undo_description()

    def redo_description(self) -> str | None:
        return self.undo_stack.redo_description()

    def undo(self) -> bool:
        """Revert the most recent Batch Edit / bulk removal / Assign
        Firmware Set / CSV import. Returns False if there was nothing to
        undo. Devices currently mid-flash are never touched by these
        operations in the first place (see __init__ docstring), so undo
        never needs to special-case a busy device."""
        snapshot = self.undo_stack.undo()
        if snapshot is None:
            return False
        self.project.devices = snapshot
        self.undo_stack_changed.emit()
        self.devices_reset.emit()
        logger.info("Undo applied")
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone operation. Returns False if
        there was nothing to redo."""
        snapshot = self.undo_stack.redo()
        if snapshot is None:
            return False
        self.project.devices = snapshot
        self.undo_stack_changed.emit()
        self.devices_reset.emit()
        logger.info("Redo applied")
        return True

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
        before = self._snapshot()
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
        self._push_undo(f"Add device '{device.name}'", before)
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

        before = self._snapshot()
        result = import_devices_from_csv(csv_path)
        for device in result.devices:
            self._apply_default_profile(device)
            self.project.add_device(device)
            self.device_added.emit(device.id)
        if result.devices:
            logger.info("Imported %d device(s) from CSV: %s", len(result.devices), csv_path)
            self._push_undo(f"Import {len(result.devices)} device(s) from CSV", before)
        return result

    def import_from_zip_bundle(self, zip_path: str) -> "ZipManifestImportResult":
        """Bulk-import devices (with their firmware already assigned) from
        a firmware bundle .zip -- see
        app.project_manager.zip_manifest_import's module docstring for the
        manifest format. Mirrors import_from_csv's per-row error model and
        undo-stack integration; unlike CSV import, each returned device
        already has its firmware list populated from the manifest, so no
        separate "Assign Firmware Set" step is needed afterward."""
        from app.project_manager.zip_manifest_import import import_devices_from_zip_bundle

        before = self._snapshot()
        result = import_devices_from_zip_bundle(zip_path)
        for device in result.devices:
            self.project.add_device(device)
            self.device_added.emit(device.id)
        if result.devices:
            logger.info("Imported %d device(s) from zip bundle: %s", len(result.devices), zip_path)
            self._push_undo(f"Import {len(result.devices)} device(s) from firmware bundle", before)
        return result

    def remove_device(self, device_id: str) -> None:
        device = self.get_device(device_id)
        if device is None:
            return
        before = self._snapshot()
        self.project.remove_device(device_id)
        logger.info("Removed device '%s' (%s)", device.name, device_id)
        self.device_removed.emit(device_id)
        self._push_undo(f"Remove device '{device.name}'", before)

    def remove_devices(self, device_ids: list[str]) -> int:
        """Bulk-remove `device_ids` in one undoable step (Devices panel's
        multi-select Remove, wired through MainWindow._on_remove_devices).
        Unlike the single-device remove_device() above, this pushes one
        UndoStack entry for the whole batch (undo restores every removed
        device at once) rather than the caller looping remove_device()
        and losing that grouping. Returns the number of devices actually
        removed."""
        before = self._snapshot()
        removed_names = []
        for device_id in device_ids:
            device = self.get_device(device_id)
            if device is None:
                continue
            self.project.remove_device(device_id)
            removed_names.append(device.name)
            self.device_removed.emit(device_id)
        if not removed_names:
            return 0
        after = self._snapshot()
        self.undo_stack.push(f"Remove {len(removed_names)} device(s)", before, after)
        self.undo_stack_changed.emit()
        logger.info("Removed %d device(s): %s", len(removed_names), ", ".join(removed_names))
        return len(removed_names)

    def duplicate_device(self, device_id: str) -> DeviceConfig | None:
        source = self.get_device(device_id)
        if source is None:
            return None
        before = self._snapshot()
        clone = source.clone()
        self.project.add_device(clone)
        logger.info("Duplicated device '%s' -> '%s'", source.name, clone.name)
        self.device_added.emit(clone.id)
        self._push_undo(f"Duplicate device '{source.name}'", before)
        return clone

    def push_device_edit_undo(
        self, device_id: str, before_device: DeviceConfig, description: str,
    ) -> bool:
        """Push one undo step for a single-device field edit made
        directly by the Device Settings / Firmware / Security panels
        (`app/ui/device_settings_widget.py`, `firmware_panel.py`,
        `security_settings_widget.py`) -- unlike Batch Edit/Assign
        Firmware Set, those panels hold a live reference to the
        DeviceConfig object itself and mutate its fields in place, so
        there's no single DeviceController method call to wrap the way
        apply_to_selected()/apply_firmware_to_devices() are wrapped.
        Instead, MainWindow captures a deep copy of the device's state
        just before an edit could happen (when it's selected -- see
        MainWindow._capture_pre_edit_snapshot) and passes that snapshot
        back in here once the panel reports the edit committed.

        Returns False (pushing nothing) if `device_id` no longer exists,
        or if the device's current state is identical to
        `before_device` -- e.g. a field's editingFinished fired without
        the value actually changing, which must not create a no-op undo
        step."""
        current = self.get_device(device_id)
        if current is None:
            return False
        if current.to_dict() == before_device.to_dict():
            return False
        before = self._snapshot()
        for index, device in enumerate(before):
            if device.id == device_id:
                before[index] = copy.deepcopy(before_device)
                break
        self._push_undo(description, before)
        return True

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
        before = self._snapshot()
        skipped = 0
        changed = 0
        for device in self.project.devices:
            if self._is_device_busy(device.id):
                skipped += 1
                continue
            if hasattr(device, predicate_field):
                setattr(device, predicate_field, value)
                self.device_updated.emit(device.id)
                changed += 1
        logger.info("Batch-applied %s=%s to %d device(s)", predicate_field, value, len(self.project.devices))
        if skipped:
            logger.warning(
                "Skipped %d device(s) mid-flash while batch-applying %s", skipped, predicate_field
            )
        if changed:
            self._push_undo(f"Batch Edit: {predicate_field}", before)

    def apply_to_selected(self, device_ids: list[str], predicate_field: str, value) -> None:
        before = self._snapshot()
        skipped = 0
        changed = 0
        for device_id in device_ids:
            if self._is_device_busy(device_id):
                skipped += 1
                continue
            device = self.get_device(device_id)
            if device is not None and hasattr(device, predicate_field):
                setattr(device, predicate_field, value)
                self.device_updated.emit(device.id)
                changed += 1
        logger.info("Batch-applied %s=%s to %d selected device(s)", predicate_field, value, len(device_ids))
        if skipped:
            logger.warning(
                "Skipped %d selected device(s) mid-flash while batch-applying %s", skipped, predicate_field
            )
        if changed:
            self._push_undo(f"Batch Edit: {predicate_field}", before)

    def _push_undo(self, description: str, before: list[DeviceConfig]) -> None:
        """Shared tail end of every undoable bulk-mutation method: capture
        the AFTER snapshot, push the UndoStack entry, and notify the UI.
        Callers pass the BEFORE snapshot they took prior to mutating."""
        after = self._snapshot()
        self.undo_stack.push(description, before, after)
        self.undo_stack_changed.emit()

    # ------------------------------------------------------------------
    # Batch-mutation preview (diff before applying) -- see ROADMAP.md's
    # "Diff / preview step for Batch Edit and Assign Firmware Set" entry.
    # These are read-only: they never mutate project state, only report
    # what a subsequent apply_to_selected/apply_firmware_to_devices/
    # add_tag_to_devices call would actually change, so the UI can show a
    # before/after confirmation table and let the user cancel with zero
    # side effects.
    # ------------------------------------------------------------------
    def preview_field_change(
        self, device_ids: list[str], predicate_field: str, value,
    ) -> list[tuple[str, str, str, str]]:
        """Return (device_id, device_name, old_value, new_value) for every
        device in `device_ids` that actually has `predicate_field` and
        whose current value differs from `value`. Busy devices are
        excluded, mirroring apply_to_selected's own skip behavior."""
        changes: list[tuple[str, str, str, str]] = []
        for device_id in device_ids:
            if self._is_device_busy(device_id):
                continue
            device = self.get_device(device_id)
            if device is None or not hasattr(device, predicate_field):
                continue
            old = getattr(device, predicate_field)
            if old == value:
                continue
            changes.append((device_id, device.name, str(old), str(value)))
        return changes

    def preview_tag_addition(self, device_ids: list[str], tag: str) -> list[tuple[str, str, str, str]]:
        """Same shape as preview_field_change, for Batch Edit's 'Tags
        (Add)' field, which appends rather than overwrites."""
        tag = tag.strip()
        changes: list[tuple[str, str, str, str]] = []
        if not tag:
            return changes
        for device_id in device_ids:
            device = self.get_device(device_id)
            if device is None or tag in device.tags:
                continue
            old = ", ".join(device.tags) if device.tags else "(none)"
            new = ", ".join([*device.tags, tag])
            changes.append((device_id, device.name, old, new))
        return changes

    def preview_firmware_assignment(
        self, device_ids: list[str], entries: list,
    ) -> list[tuple[str, str, str, str]]:
        """Same shape as preview_field_change, for Assign Firmware Set to
        Devices: compares each target device's current firmware list
        against the incoming `entries` (as produced by
        scan_firmware_folder()) and reports only devices whose resulting
        firmware list would actually differ."""

        def _summary(firmware_list) -> str:
            if not firmware_list:
                return "(none)"
            return ", ".join(f"{e.file_name}@{e.address}" for e in firmware_list)

        new_summary = _summary(entries)
        changes: list[tuple[str, str, str, str]] = []
        for device_id in device_ids:
            if self._is_device_busy(device_id):
                continue
            device = self.get_device(device_id)
            if device is None:
                continue
            old_summary = _summary(device.firmware)
            if old_summary == new_summary:
                continue
            changes.append((device_id, device.name, old_summary, new_summary))
        return changes

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
        before = self._snapshot()
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
        if updated:
            self._push_undo("Assign Firmware Set", before)
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
        before = self._snapshot()
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
        if updated:
            self._push_undo(f"Batch Edit: add tag '{tag}'", before)
        return updated
