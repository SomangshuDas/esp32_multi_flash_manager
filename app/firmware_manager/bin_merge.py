"""
bin_merge.py
=============
"Merge Bins": combine a device's separate firmware images (bootloader,
partition table, app, ...) into one flashable .bin via esptool's own
`merge-bin` command, entirely offline (no board connection needed).

This module owns:
  - MergeReport / validate_merge_entries: pre-merge sanity checks (missing
    files, invalid/duplicate addresses, byte-range overlaps, no chip
    selected, bad output path) so a broken merge is caught before esptool
    is even invoked, with clear per-issue messages -- mirroring
    app/flash_engine/validator.py's pre-upload checks.
  - run_merge: builds the esptool command (via FlashCommandBuilder) and
    runs it synchronously (merging is a fast, local, CPU/disk-bound
    operation, not a multi-minute serial transfer, so this deliberately
    does NOT need its own QThread worker the way flashing does).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from app.flash_engine.esptool_wrapper import FlashCommandBuilder
from app.logging_setup.logger import get_logger
from app.models.firmware_model import FirmwareEntry
from app.utilities.chip_detect import AUTO_CHIP
from app.utilities.helpers import is_valid_hex_address

logger = get_logger(__name__)

# esptool merge-bin can hang if it's ever fed a bad/interactive argument;
# capped generously since even large (multi-MB, many-file) merges finish
# in well under a minute on local disk.
MERGE_TIMEOUT_SECONDS = 180


class MergeSeverity(Enum):
    ERROR = "Error"
    WARNING = "Warning"


@dataclass
class MergeIssue:
    severity: MergeSeverity
    message: str


@dataclass
class MergeReport:
    issues: list[MergeIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == MergeSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == MergeSeverity.WARNING for i in self.issues)

    def add_error(self, message: str) -> None:
        self.issues.append(MergeIssue(MergeSeverity.ERROR, message))

    def add_warning(self, message: str) -> None:
        self.issues.append(MergeIssue(MergeSeverity.WARNING, message))


def validate_merge_entries(
    entries: list[FirmwareEntry],
    chip: str,
    output_path: str,
) -> MergeReport:
    """
    Validate a set of firmware entries + a chosen chip/output path before
    handing them to esptool. Returns a MergeReport; ERROR-level issues must
    block the merge, WARNING-level issues should be confirmed by the user.
    """
    report = MergeReport()

    if not entries:
        report.add_error("Select at least one firmware file to merge.")
        return report

    if not chip or chip == AUTO_CHIP:
        report.add_error(
            "A specific chip must be selected for merging (not \"auto\") -- esptool needs to "
            "know the target chip to lay out the merged image correctly."
        )

    if not output_path or not output_path.strip():
        report.add_error("Choose an output file name/location for the merged .bin.")
    else:
        output_dir = Path(output_path).expanduser().parent
        if not output_dir.exists():
            report.add_error(f"Output folder does not exist: {output_dir}")
        elif not output_dir.is_dir():
            report.add_error(f"Output location is not a folder: {output_dir}")
        elif Path(output_path).is_dir():
            report.add_error(f"Output path is a folder, not a file: {output_path}")
        elif Path(output_path).exists():
            report.add_warning(f"Output file already exists and will be overwritten: {output_path}")

    # Per-file checks: missing files, invalid/duplicate addresses.
    seen_addresses: dict[str, str] = {}
    ranges: list[tuple[int, int, str]] = []  # (start, end_exclusive, file_name)
    for entry in entries:
        if not entry.file_path:
            report.add_error("A selected row has no file.")
            continue
        if not Path(entry.file_path).is_file():
            report.add_error(f"Firmware file missing on disk: {entry.file_path}")
            continue
        if not is_valid_hex_address(entry.address):
            report.add_error(f"Invalid flash address '{entry.address}' for {entry.file_name}.")
            continue

        norm = entry.address.lower()
        if norm in seen_addresses:
            report.add_error(
                f"Duplicate flash address {entry.address} used by both "
                f"'{seen_addresses[norm]}' and '{entry.file_name}'."
            )
        else:
            seen_addresses[norm] = entry.file_name

        try:
            size = Path(entry.file_path).stat().st_size
        except OSError as exc:
            report.add_error(f"Could not read '{entry.file_name}': {exc}")
            continue
        if size == 0:
            report.add_warning(f"'{entry.file_name}' is 0 bytes.")
        start = int(norm, 16)
        ranges.append((start, start + size, entry.file_name))

    # Byte-range overlap detection (same approach as the pre-upload
    # validator: sort by start address, compare each entry to its
    # immediate neighbour).
    ranges.sort(key=lambda r: r[0])
    for (start_a, end_a, name_a), (start_b, end_b, name_b) in zip(ranges, ranges[1:]):
        if start_b < end_a:
            report.add_error(
                f"'{name_a}' (ends at 0x{end_a:x}) overlaps '{name_b}' (starts at 0x{start_b:x}). "
                "Fix the addresses so no two files occupy the same flash region."
            )

    return report


def firmware_bin_folder(entries: list[FirmwareEntry]) -> str | None:
    """
    Locate the folder "firmware.bin" lives in among `entries` (the app's
    conventional main-app image address/name -- see
    KNOWN_FIRMWARE_ADDRESSES in constants.py), used as the default Bin
    Merge output location. Falls back to the folder of the first entry
    with a file path if no file is literally named firmware.bin, and to
    None if there's nothing to go on at all.
    """
    fallback: str | None = None
    for entry in entries:
        if not entry.file_path:
            continue
        path = Path(entry.file_path)
        if fallback is None:
            fallback = str(path.parent)
        if path.name.lower() == "firmware.bin":
            return str(path.parent)
    return fallback


@dataclass
class MergeResult:
    success: bool
    output_path: str
    command: list[str]
    output_text: str
    error_message: str = ""


def run_merge(
    entries: list[FirmwareEntry],
    chip: str,
    output_path: str,
    flash_mode: str = "keep",
    flash_frequency: str = "keep",
    flash_size: str = "keep",
) -> MergeResult:
    """
    Run `esptool --chip <chip> merge-bin` synchronously and return the
    result. Callers (the Merge Bins dialog) are expected to have already
    validated with validate_merge_entries() and to show a busy cursor
    around this call, since it blocks the calling thread for the (usually
    sub-second, at most a few seconds) duration of the merge.
    """
    address_file_pairs = [(entry.address, entry.file_path) for entry in entries]
    command = FlashCommandBuilder.build_merge_bin_args(
        chip=chip,
        entries=address_file_pairs,
        output_path=output_path,
        flash_mode=flash_mode,
        flash_frequency=flash_frequency,
        flash_size=flash_size,
    )
    logger.info("Running bin merge: %s", " ".join(command))

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=MERGE_TIMEOUT_SECONDS,
            creationflags=creationflags,
        )
    except FileNotFoundError as exc:
        logger.exception("esptool executable/module not found while merging")
        return MergeResult(
            success=False, output_path=output_path, command=command, output_text="",
            error_message=f"esptool could not be launched (is it installed?): {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("Bin merge timed out")
        return MergeResult(
            success=False, output_path=output_path, command=command,
            output_text=exc.output or "",
            error_message=f"Merge timed out after {MERGE_TIMEOUT_SECONDS}s.",
        )
    except Exception as exc:  # noqa: BLE001 - merge must never crash the app
        logger.exception("Unexpected error while merging bins")
        return MergeResult(
            success=False, output_path=output_path, command=command, output_text="",
            error_message=f"Unexpected error: {exc}",
        )

    output_text = completed.stdout or ""
    if completed.returncode == 0 and Path(output_path).is_file():
        return MergeResult(success=True, output_path=output_path, command=command, output_text=output_text)

    error_message = f"esptool merge-bin exited with code {completed.returncode}."
    return MergeResult(
        success=False, output_path=output_path, command=command,
        output_text=output_text, error_message=error_message,
    )
