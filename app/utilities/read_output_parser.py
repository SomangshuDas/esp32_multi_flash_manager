"""
read_output_parser.py
======================
Best-effort parser that turns the raw text `esptool`/`espefuse` print to
stdout for a Read Device operation (see app/workers/read_worker.py) into a
short list of friendly (label, value) rows, for the Read Device dialog's
**Summary** tab (app/ui/read_device_dialog.py). The **Log** tab always
keeps showing the complete, unmodified command output -- this module never
replaces that, it only extracts the handful of fields a human actually
scans for out of it.

Every function here is pure text-in/rows-out and touches no hardware,
Qt, or subprocess -- it only runs after ReadWorker has already captured
the tool's output. Parsing is intentionally forgiving: esptool/espefuse
output wording has shifted across versions and chips, so every regex is
optional and a field that can't be found is simply omitted from the
summary rather than raising. Nothing here is used for any safety-relevant
decision -- see parse_security_state_from_output in security_manager.py
for the one parse result (flash-encryption / secure-boot state) that
actually feeds a warning elsewhere in the app; this module is display-only.
"""

from __future__ import annotations

import re

from app.utilities.constants import (
    READ_MODE_CHIP_INFO,
    READ_MODE_EFUSE_SUMMARY,
    READ_MODE_FLASH_ID,
    READ_MODE_READ_FLASH,
    READ_MODE_SECURITY_INFO,
)
from app.utilities.helpers import human_readable_duration, human_readable_size

# Lines ReadWorker/ReadDeviceDialog add themselves (command echo, cancel/
# failure notes, "Saved to:" footer) rather than tool output -- stripped
# before parsing so they can never be mistaken for a real field.
_OWN_LINE_PREFIXES = (">>>",)

# espefuse `summary` fields worth surfacing. Keys are matched
# case-insensitively against the eFuse name at the start of each row; the
# label is what's shown in the Summary tab.
_EFUSE_FIELDS_OF_INTEREST = (
    ("MAC", "MAC Address"),
    ("MAC_FACTORY", "MAC Address"),
    ("FLASH_CRYPT_CNT", "Flash Encryption Counter"),
    ("SPI_BOOT_CRYPT_CNT", "Flash Encryption Counter"),
    ("SECURE_BOOT_EN", "Secure Boot Enabled"),
    ("ABS_DONE_0", "Secure Boot V1 Enabled"),
    ("ABS_DONE_1", "Secure Boot V2 Enabled"),
    ("DISABLE_DL_ENCRYPT", "Download-Mode Encrypt Disabled"),
    ("DISABLE_DL_DECRYPT", "Download-Mode Decrypt Disabled"),
    ("DISABLE_DL_CACHE", "Download-Mode Cache Disabled"),
    ("JTAG_DISABLE", "JTAG Disabled"),
    ("CHIP_VER", "Chip Revision"),
    ("WAFER_VERSION", "Wafer Revision"),
    ("FLASH_CAP", "Flash Capacity Code"),
    ("WR_DIS", "Write-Protected eFuse Blocks"),
    ("RD_DIS", "Read-Protected eFuse Blocks"),
)

# esptool prints "MAC: xx:xx:xx:xx:xx:xx" (or "MAC address: ...") during the
# connect phase of EVERY command that talks to a chip -- Chip Info reads,
# Read Flash Region, and (notably) `write_flash` itself. This single regex
# is shared by _parse_chip_info's Summary-tab row below AND by
# app/controllers/flash_controller.py, which scans a normal flashing run's
# own log output for it to capture device traceability (see
# extract_mac_address()) without needing a separate Read operation.
_MAC_ADDRESS_PATTERN = r"mac(?:\s*address)?:\s*([0-9a-f:]{17})"


def _clean_lines(raw_text: str) -> list[str]:
    lines = []
    for line in (raw_text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(_OWN_LINE_PREFIXES):
            continue
        lines.append(stripped)
    return lines


def _first_match(pattern: str, lines: list[str], flags: int = re.IGNORECASE) -> str | None:
    for line in lines:
        match = re.search(pattern, line, flags)
        if match:
            return match.group(1).strip()
    return None


def _parse_chip_info(lines: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    chip_line = _first_match(r"chip is\s+(.+?)(?:\s*\(revision|\s*$)", lines)
    if chip_line:
        rows.append(("Chip Model", chip_line))

    revision = _first_match(r"\(revision\s+([^)]+)\)", lines)
    if revision:
        rows.append(("Silicon Revision", revision))

    features = _first_match(r"features:\s*(.+)", lines)
    if features:
        rows.append(("Features", features))

    crystal = _first_match(r"crystal is\s+(.+)", lines)
    if crystal:
        rows.append(("Crystal Frequency", crystal))

    mac = _first_match(_MAC_ADDRESS_PATTERN, lines)
    if mac:
        rows.append(("MAC Address", mac))

    chip_id = _first_match(r"chip id:\s*(0x[0-9a-f]+)", lines)
    if chip_id:
        rows.append(("Chip ID", chip_id))

    return rows


def _parse_flash_id(lines: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    manufacturer = _first_match(r"manufacturer:\s*([0-9a-fx]+)", lines)
    if manufacturer:
        rows.append(("Flash Manufacturer ID", manufacturer))

    device = _first_match(r"device:\s*([0-9a-fx]+)", lines)
    if device:
        rows.append(("Flash Device ID", device))

    detected_size = _first_match(r"detected flash size:\s*(.+)", lines)
    if detected_size:
        rows.append(("Detected Flash Size", detected_size))

    flash_type = _first_match(r"flash type set in eFuse:\s*(.+)", lines)
    if flash_type:
        rows.append(("Flash Type (eFuse)", flash_type))

    voltage = _first_match(r"flash voltage set by eFuse to\s*(.+)", lines)
    if voltage:
        rows.append(("Flash Voltage (eFuse)", voltage))

    return rows


def _parse_security_info(lines: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    flags = _first_match(r"flags?:\s*(0x[0-9a-f]+)", lines)
    if flags:
        rows.append(("Security Flags", flags))

    for pattern, label in (
        (r"secure_boot_en\s*[:=]\s*(\w+)", "Secure Boot Enabled"),
        (r"secure boot\s*[:=]\s*(\w+)", "Secure Boot Enabled"),
        (r"flash_crypt_cnt\s*[:=]\s*(\w+)", "Flash Encryption Counter"),
        (r"flash encryption\s*[:=]\s*(\w+)", "Flash Encryption"),
        (r"secure_boot_aggressive_revoke\s*[:=]\s*(\w+)", "Secure Boot Aggressive Revoke"),
        (r"secure_download_mode\s*[:=]\s*(\w+)", "Secure Download Mode"),
        (r"jtag_disabled?\s*[:=]\s*(\w+)", "JTAG Disabled"),
        (r"dl_encrypt_disabled?\s*[:=]\s*(\w+)", "Download-Mode Encrypt Disabled"),
        (r"dl_decrypt_disabled?\s*[:=]\s*(\w+)", "Download-Mode Decrypt Disabled"),
        (r"chip id:\s*(0x[0-9a-f]+)", "Chip ID"),
        (r"api version:\s*(\w+)", "Security Info API Version"),
    ):
        value = _first_match(pattern, lines)
        if value:
            rows.append((label, value))

    return rows


def _extract_efuse_value(line: str) -> str | None:
    """
    espefuse `summary` rows put the value after an `=` sign, followed by an
    R/W marker and/or a parenthesized note -- e.g.
    `= 24:0a:c4:00:11:22 R/W` or `= 0 R/W (0x0)`. Depending on espefuse
    version/terminal width this `=` can be on the same line as the field
    name or wrapped onto the following line, so callers check both.
    """
    match = re.search(r"=\s*([^\s(]+(?:\s[^\s(]+)*?)\s*(?:R/W|R/-|-/W|\(|$)", line)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _parse_efuse_summary(lines: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen_labels: set[str] = set()

    for index, line in enumerate(lines):
        field_name = line.split()[0].upper() if line.split() else ""
        for key, label in _EFUSE_FIELDS_OF_INTEREST:
            if field_name != key or label in seen_labels:
                continue
            # espefuse summary rows look like:
            #   FIELD_NAME (BLOCKn)   Description   = value  R/W (extra)
            # but the "= value" part sometimes wraps onto the next line.
            value = _extract_efuse_value(line)
            if value is None and index + 1 < len(lines):
                value = _extract_efuse_value(lines[index + 1])
            if value:
                rows.append((label, value))
                seen_labels.add(label)
            break

    return rows


def _parse_read_flash(
    lines: list[str], *, address: str = "", size: str = "", output_path: str = "",
    duration_seconds: float | None = None,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if address:
        rows.append(("Start Address", address))
    if size:
        rows.append(("Requested Size", size))
        size_bytes = _try_parse_int(size)
        if size_bytes is not None:
            rows.append(("Requested Size (bytes)", human_readable_size(size_bytes)))
    if output_path:
        rows.append(("Saved To", output_path))
    if duration_seconds is not None:
        rows.append(("Duration", human_readable_duration(duration_seconds)))
    return rows


def _try_parse_int(value: str) -> int | None:
    value = (value or "").strip()
    try:
        if value.lower().startswith("0x"):
            return int(value, 16)
        return int(value, 10)
    except ValueError:
        return None


def parse_read_output(
    mode: str,
    raw_text: str,
    *,
    address: str = "",
    size: str = "",
    output_path: str = "",
    duration_seconds: float | None = None,
) -> list[tuple[str, str]]:
    """
    Parse `raw_text` (the accumulated Log tab contents for one Read Device
    run) for `mode` (a READ_MODE_* constant) into a list of (label, value)
    rows suitable for display in the Summary tab. Returns an empty list if
    nothing recognizable was found -- callers should fall back to pointing
    the user at the Log tab in that case, never treat an empty list as an
    error.
    """
    if mode == READ_MODE_READ_FLASH:
        # Read Flash's raw output is just progress percentages -- the
        # useful summary comes from the request/result context, not from
        # parsing tool output, so this mode never needs `lines` at all.
        return _parse_read_flash(
            _clean_lines(raw_text), address=address, size=size, output_path=output_path,
            duration_seconds=duration_seconds,
        )

    lines = _clean_lines(raw_text)
    if not lines:
        return []

    if mode == READ_MODE_CHIP_INFO:
        return _parse_chip_info(lines)
    if mode == READ_MODE_FLASH_ID:
        return _parse_flash_id(lines)
    if mode == READ_MODE_SECURITY_INFO:
        return _parse_security_info(lines)
    if mode == READ_MODE_EFUSE_SUMMARY:
        return _parse_efuse_summary(lines)
    return []


def extract_mac_address(raw_text: str) -> str | None:
    """
    Scan `raw_text` (any esptool/espefuse output -- Chip Info, Read Flash,
    or a plain `write_flash` run) for a "MAC: xx:xx:xx:xx:xx:xx" line and
    return the address, or None if not found. Never raises.

    This is the SAME regex used by the Chip Info Summary tab
    (_parse_chip_info above) -- it's factored out here so
    FlashController can reuse it for Device Traceability (attaching the
    MAC address to a flash history entry) without duplicating the pattern
    or requiring a separate Read Flash/eFuse operation to run first.
    """
    try:
        return _first_match(_MAC_ADDRESS_PATTERN, _clean_lines(raw_text))
    except Exception:  # noqa: BLE001 - never let a parsing hiccup break a flash job
        return None
