"""
chip_detect.py
===============
Dynamic chip-support detection.

Chip Type dropdowns used to be a hardcoded list (SUPPORTED_CHIPS in
constants.py) that only ever grew when someone remembered to edit it after
a new esptool release. That silently went stale: esptool itself gains new
chip targets (esp32c5, esp32p4, ...) far more often than this app gets a
new release, so the dropdown and the validator could both be wrong about
what the bundled esptool can actually flash.

detect_supported_chips() asks the installed `esptool` package directly
(esptool.targets.CHIP_LIST) at startup instead. This is an in-process
import purely for introspection -- it never launches the esptool
subprocess used for actual flashing (see esptool_wrapper.py), so it's
cheap and safe to call once when the app starts.

If esptool can't be imported for some reason (broken install), detection
falls back to the hardcoded SUPPORTED_CHIPS list so the app still starts
and functions, just without newly-added chips until esptool is fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.logging_setup.logger import get_logger
from app.utilities.constants import SUPPORTED_CHIPS

logger = get_logger(__name__)

# "auto" is not a real chip target -- it's esptool's own CLI convention for
# "figure out the chip by talking to it first". It is not part of
# esptool.targets.CHIP_LIST, so it's added back in manually here.
AUTO_CHIP = "auto"


@dataclass
class ChipDetectionResult:
    chips: list[str] = field(default_factory=lambda: list(SUPPORTED_CHIPS))
    dynamic: bool = False          # True if this came from esptool itself
    esptool_version: str | None = None
    error: str | None = None       # human-readable reason detection fell back


def detect_supported_chips() -> ChipDetectionResult:
    """
    Return the list of chip identifiers the installed esptool actually
    supports (with "auto" first), plus metadata about how that list was
    obtained. Never raises -- any failure is reported via `.error` and the
    hardcoded fallback list is returned instead.
    """
    try:
        from esptool.targets import CHIP_LIST  # type: ignore[import-not-found]

        try:
            from esptool import __version__ as esptool_version  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - version string is informational only
            esptool_version = None

        chips = [AUTO_CHIP] + sorted(CHIP_LIST)
        logger.info(
            "Detected %d supported chip(s) from esptool%s: %s",
            len(chips) - 1,
            f" v{esptool_version}" if esptool_version else "",
            ", ".join(chips),
        )
        return ChipDetectionResult(chips=chips, dynamic=True, esptool_version=esptool_version)
    except Exception as exc:  # noqa: BLE001 - esptool import must never crash startup
        logger.warning(
            "Could not dynamically detect chip support from esptool (%s); "
            "falling back to the built-in chip list.", exc,
        )
        return ChipDetectionResult(
            chips=list(SUPPORTED_CHIPS), dynamic=False, error=str(exc),
        )


def find_unsupported_chips(devices, supported_chips: list[str]) -> dict[str, str]:
    """
    Given a project's devices and the currently-detected supported chip
    list, return {device_name: chip_type} for every device whose configured
    chip is neither "auto" nor in `supported_chips` -- i.e. a chip the
    installed esptool can no longer (or never could) flash. Used to warn
    the user clearly instead of letting them discover it only when Upload
    fails.
    """
    unsupported: dict[str, str] = {}
    supported_set = set(supported_chips)
    for device in devices:
        chip = getattr(device, "chip_type", "") or ""
        if not chip or chip == AUTO_CHIP:
            continue
        if chip not in supported_set:
            unsupported[device.name] = chip
    return unsupported
