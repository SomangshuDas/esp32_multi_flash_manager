"""
security_manager.py
====================
Flash encryption / secure boot provisioning, built entirely on top of the
official `espsecure` and `espefuse` command-line tools (both ship inside
the same `esptool` PyPI package this app already depends on). This module
never implements any cryptographic primitive, key-derivation, or eFuse
wire-protocol logic itself -- it only builds argument lists for those
tools and (for the offline, no-hardware operations) runs them, exactly the
same design as FlashCommandBuilder / bin_merge.py do for `esptool` itself.

Command mapping (espsecure/espefuse 5.x, hyphenated Click-style names --
matches the `esptool>=5.0.0` pin in requirements.txt):

  Key generation (offline, no device):
    espsecure generate-flash-encryption-key <keyfile>
    espsecure generate-signing-key --version {1,2} [--scheme ...] <keyfile>

  Image signing for Secure Boot (offline, no device):
    espsecure sign-data --version {1,2} --keyfile <key> -o <out> <in>

  Burning eFuses (ONLINE -- talks to real hardware, irreversible):
    Legacy ESP32:
      espefuse --port P burn-key flash_encryption   <keyfile> --no-protect-key?
      espefuse --port P burn-key secure_boot_v1|v2   <keyfile>
    Unified eFuse table chips (S2/S3/C3/C6/H2/...):
      espefuse --port P burn-key-digest BLOCK_KEYn <keyfile> <PURPOSE>
      espefuse --port P burn-key        BLOCK_KEYn <keyfile> XTS_AES_256_KEY

  Reading back (ONLINE, read-only):
    espefuse --port P summary
    espefuse --port P dump

Everything that touches real hardware (burn-key / burn-key-digest /
burn-efuse) is run through the same FlashProcess/QThread pattern as actual
flashing (see app/workers/security_worker.py), never synchronously, and is
always preceded by this app's own explicit UI confirmation (see
app/ui/provision_confirm_dialog.py) plus `--do-not-confirm` passed to
espefuse itself -- that flag *skips espefuse's own interactive terminal
prompt*, which would otherwise hang forever against a piped subprocess; it
does not skip any safety check inside espefuse, and it is never used
without this app's own confirmation dialog having already been accepted.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.flash_engine.esptool_wrapper import espsecure_command_prefix
from app.logging_setup.logger import get_logger
from app.models.device_model import DeviceConfig
from app.utilities.constants import (
    LEGACY_BLOCK_FLASH_ENCRYPTION,
    LEGACY_BLOCK_SECURE_BOOT_V1,
    LEGACY_BLOCK_SECURE_BOOT_V2,
    LEGACY_EFUSE_CHIPS,
    UNIFIED_KEY_PURPOSE_FLASH_ENCRYPTION,
    UNIFIED_KEY_PURPOSE_SECURE_BOOT_V2,
)

logger = get_logger(__name__)

# Offline key-gen/signing is fast, local, and CPU-bound -- capped generously
# the same way bin_merge.py caps its own offline esptool call.
OFFLINE_TIMEOUT_SECONDS = 60


def is_legacy_efuse_chip(chip_type: str) -> bool:
    """True if `chip_type` uses espefuse's legacy fixed-block-name scheme
    (currently just the original ESP32) rather than the unified eFuse
    table (BLOCK_KEYn + explicit key-purpose) every newer chip uses."""
    return (chip_type or "").lower() in LEGACY_EFUSE_CHIPS


class SecurityCommandBuilder:
    """Builds `espsecure`/`espefuse` CLI argument lists. Mirrors
    FlashCommandBuilder's role for `esptool` -- see this module's
    docstring for the exact commands each method maps to."""

    # ------------------------------------------------------------------
    # Offline: key generation / image signing (no device connection)
    # ------------------------------------------------------------------
    @staticmethod
    def build_generate_flash_encryption_key_args(output_path: str) -> list[str]:
        args = espsecure_command_prefix()
        args += ["generate-flash-encryption-key", output_path]
        return args

    @staticmethod
    def build_generate_signing_key_args(output_path: str, version: str, scheme: str = "") -> list[str]:
        args = espsecure_command_prefix()
        args += ["generate-signing-key", "--version", version]
        # --scheme only applies to Secure Boot V2; V1 is always RSA-3072.
        if version == "2" and scheme:
            args += ["--scheme", scheme]
        args += [output_path]
        return args

    @staticmethod
    def build_sign_data_args(input_path: str, output_path: str, keyfile: str, version: str) -> list[str]:
        args = espsecure_command_prefix()
        args += ["sign-data", "--version", version, "--keyfile", keyfile, "--output", output_path, input_path]
        return args

    # ------------------------------------------------------------------
    # Online: burning eFuses (irreversible -- see module docstring)
    # ------------------------------------------------------------------
    @staticmethod
    def build_burn_flash_encryption_key_args(device: DeviceConfig) -> list[str]:
        """
        Burn the flash-encryption AES key into the correct eFuse block for
        `device.chip_type`. Uses the legacy fixed-block form for the
        original ESP32, and the unified BLOCK_KEYn + explicit purpose form
        for every other supported chip.
        """
        sec = device.security
        args = ["--port", device.com_port, "--baud", str(device.baud_rate)]
        if device.chip_type and device.chip_type != "auto":
            args = ["--chip", device.chip_type] + args
        args += ["--do-not-confirm"]  # this app's own dialog is the confirmation gate -- see module docstring
        # espefuse read/write-protects a burned key by default -- the safe
        # default (RECOMMENDED for production use). keep_key_readable opts
        # OUT of that protection, matching espefuse's own opt-out flags.
        if sec.keep_key_readable:
            args += ["--no-protect-key"] if is_legacy_efuse_chip(device.chip_type) else ["--no-read-protect"]

        from app.flash_engine.esptool_wrapper import espefuse_command_prefix
        prefix = espefuse_command_prefix()

        if is_legacy_efuse_chip(device.chip_type):
            args += ["burn-key", LEGACY_BLOCK_FLASH_ENCRYPTION, sec.flash_encryption_key_path]
        else:
            # Unified eFuse table chips: burn-key takes an explicit
            # key-purpose alongside the block + keyfile. XTS_AES_256_KEY is
            # the purpose for a raw 256-bit flash-encryption key.
            args += [
                "burn-key",
                sec.flash_encryption_key_block,
                sec.flash_encryption_key_path,
                UNIFIED_KEY_PURPOSE_FLASH_ENCRYPTION,
            ]
        if sec.custom_efuse_args.strip():
            args += sec.custom_efuse_args.strip().split()
        return prefix + args

    @staticmethod
    def build_burn_secure_boot_key_args(device: DeviceConfig) -> list[str]:
        """Burn the secure-boot (signing) public-key digest into the
        correct eFuse block, legacy or unified scheme as above."""
        sec = device.security
        args = ["--port", device.com_port, "--baud", str(device.baud_rate)]
        if device.chip_type and device.chip_type != "auto":
            args = ["--chip", device.chip_type] + args
        args += ["--do-not-confirm"]

        from app.flash_engine.esptool_wrapper import espefuse_command_prefix
        prefix = espefuse_command_prefix()

        if is_legacy_efuse_chip(device.chip_type):
            block = LEGACY_BLOCK_SECURE_BOOT_V1 if sec.secure_boot_version == "1" else LEGACY_BLOCK_SECURE_BOOT_V2
            args += ["burn-key", block, sec.secure_boot_key_path]
        else:
            # burn-key-digest computes the digest of the given public-key
            # file at burn time -- the correct form for Secure Boot V2,
            # which stores a key digest in eFuse, not the raw key itself.
            args += [
                "burn-key-digest",
                sec.secure_boot_key_block,
                sec.secure_boot_key_path,
                UNIFIED_KEY_PURPOSE_SECURE_BOOT_V2,
            ]
        if sec.custom_efuse_args.strip():
            args += sec.custom_efuse_args.strip().split()
        return prefix + args

    @staticmethod
    def build_burn_efuse_flag_args(device: DeviceConfig, efuse_name: str, value: str = "1") -> list[str]:
        """
        Burn a single boolean/enum-style eFuse (e.g. enabling Secure Boot
        or locking Flash Encryption into release mode). This is a
        deliberately generic passthrough -- the exact eFuse name to burn
        differs per chip family and espefuse itself is the authority on
        what's valid (`espefuse --chip <chip> burn-efuse --help` lists the
        allowed names), so this app does not hardcode a fixed set.
        """
        from app.flash_engine.esptool_wrapper import espefuse_command_prefix
        prefix = espefuse_command_prefix()
        args = ["--port", device.com_port, "--baud", str(device.baud_rate)]
        if device.chip_type and device.chip_type != "auto":
            args = ["--chip", device.chip_type] + args
        args += ["--do-not-confirm", "burn-efuse", efuse_name, value]
        return prefix + args

    # ------------------------------------------------------------------
    # Online, read-only
    # ------------------------------------------------------------------
    @staticmethod
    def build_efuse_summary_args(device: DeviceConfig, output_path: str = "") -> list[str]:
        from app.flash_engine.esptool_wrapper import espefuse_command_prefix
        prefix = espefuse_command_prefix()
        args = ["--port", device.com_port, "--baud", str(device.baud_rate)]
        if device.chip_type and device.chip_type != "auto":
            args = ["--chip", device.chip_type] + args
        args += ["summary"]
        if output_path:
            args += ["--file", output_path]
        return prefix + args

    @staticmethod
    def build_efuse_dump_args(device: DeviceConfig, output_path: str = "") -> list[str]:
        from app.flash_engine.esptool_wrapper import espefuse_command_prefix
        prefix = espefuse_command_prefix()
        args = ["--port", device.com_port, "--baud", str(device.baud_rate)]
        if device.chip_type and device.chip_type != "auto":
            args = ["--chip", device.chip_type] + args
        args += ["dump"]
        if output_path:
            args += ["--file-name", output_path]
        return prefix + args


@dataclass
class OfflineSecurityResult:
    success: bool
    command: list[str]
    output_text: str
    error_message: str = ""


def _run_offline(command: list[str]) -> OfflineSecurityResult:
    """Run an offline (no hardware) espsecure command synchronously --
    same pattern as bin_merge.run_merge(), since key generation/signing
    completes in well under a second and needs no cancel/progress UI."""
    logger.info("Running offline security command: %s", " ".join(command))
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=OFFLINE_TIMEOUT_SECONDS,
            creationflags=creationflags,
        )
    except FileNotFoundError as exc:
        logger.exception("espsecure executable/module not found")
        return OfflineSecurityResult(
            success=False, command=command, output_text="",
            error_message=f"espsecure could not be launched (is it installed?): {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception("Offline security command timed out")
        return OfflineSecurityResult(
            success=False, command=command, output_text=exc.output or "",
            error_message=f"Command timed out after {OFFLINE_TIMEOUT_SECONDS}s.",
        )
    except Exception as exc:  # noqa: BLE001 - must never crash the app
        logger.exception("Unexpected error running offline security command")
        return OfflineSecurityResult(
            success=False, command=command, output_text="", error_message=f"Unexpected error: {exc}",
        )

    output_text = completed.stdout or ""
    if completed.returncode == 0:
        return OfflineSecurityResult(success=True, command=command, output_text=output_text)
    return OfflineSecurityResult(
        success=False, command=command, output_text=output_text,
        error_message=f"espsecure exited with code {completed.returncode}.",
    )


def generate_flash_encryption_key(output_path: str) -> OfflineSecurityResult:
    """Generate a new random AES flash-encryption key file via
    `espsecure generate-flash-encryption-key`. The key material itself is
    produced entirely by espsecure -- this function only invokes it."""
    Path(output_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    command = SecurityCommandBuilder.build_generate_flash_encryption_key_args(output_path)
    return _run_offline(command)


def generate_signing_key(output_path: str, version: str, scheme: str = "") -> OfflineSecurityResult:
    """Generate a new secure-boot signing key via
    `espsecure generate-signing-key`."""
    Path(output_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    command = SecurityCommandBuilder.build_generate_signing_key_args(output_path, version, scheme)
    return _run_offline(command)


def sign_firmware_image(input_path: str, output_path: str, keyfile: str, version: str) -> OfflineSecurityResult:
    """Sign a bootloader/app image for Secure Boot via `espsecure
    sign-data`. The signature itself is computed entirely by espsecure."""
    Path(output_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    command = SecurityCommandBuilder.build_sign_data_args(input_path, output_path, keyfile, version)
    return _run_offline(command)


# --------------------------------------------------------------------------
# Pre-provisioning validation -- see app/flash_engine/validator.py for how
# this is wired into the shared pre-upload/pre-provision report. Kept in
# this module (rather than validator.py) since it is specific to security
# settings and needs no hardware/port state, only the device's own config.
# --------------------------------------------------------------------------


def expected_key_sizes_bytes() -> tuple[int, ...]:
    """AES-XTS key file sizes esptool/espsecure actually produce/accept for
    flash encryption: 32 bytes (AES-256, the default on every chip) or 64
    bytes (AES-256 dual-key XTS mode, available on some newer chips). Used
    only as a loose sanity check, not a hard chip-specific validation --
    espefuse itself is the final authority when the key is actually burned.
    """
    return (32, 64)


def parse_security_state_from_output(text: str) -> tuple[bool | None, bool | None]:
    """
    Best-effort parse of `esptool get-security-info` / `espefuse summary`
    text output into (flash_encryption_enabled, secure_boot_enabled).
    Returns None for either value when it can't be determined confidently
    from the text -- callers must treat None as "unknown", not "disabled".
    This only feeds the pre-upload "device already encrypted" warning
    (see validate_security_settings); it is never used to decide whether
    it's safe to burn anything.
    """
    flash_encryption: bool | None = None
    secure_boot: bool | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip().lower()
        if not line:
            continue
        if "flash_crypt_cnt" in line or "flash encryption" in line:
            if "enabled" in line or ("true" in line and "disabled" not in line):
                flash_encryption = True
            elif "disabled" in line or "false" in line:
                flash_encryption = False
        if "secure_boot_en" in line or "secure boot" in line:
            if "enabled" in line or ("true" in line and "disabled" not in line):
                secure_boot = True
            elif "disabled" in line or "false" in line:
                secure_boot = False
    return flash_encryption, secure_boot


@dataclass
class SecurityValidationIssue:
    is_error: bool
    message: str


@dataclass
class SecurityValidationReport:
    issues: list[SecurityValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.is_error for i in self.issues)

    def add_error(self, message: str) -> None:
        self.issues.append(SecurityValidationIssue(True, message))

    def add_warning(self, message: str) -> None:
        self.issues.append(SecurityValidationIssue(False, message))


def validate_security_settings(device: DeviceConfig) -> SecurityValidationReport:
    """
    Pre-flight sanity checks for a device's SecurityConfig, run before any
    key generation, signing, or eFuse burning. Pure and offline -- reads
    only the local filesystem (to check key files) and the device's own
    in-memory config/runtime state, never touches hardware. See the
    requirements this implements in the module/PR description: missing key
    files, key/chip size mismatches, and flashing unencrypted firmware to a
    device already showing flash encryption enabled.
    """
    report = SecurityValidationReport()
    sec = device.security

    if not sec.enable_flash_encryption and not sec.enable_secure_boot:
        # Nothing security-related requested for this device -- still worth
        # flagging the single most dangerous foot-gun even when the user
        # hasn't touched these settings at all: a device this app has
        # previously read back as flash-encryption-enabled, about to
        # receive a plain, unencrypted write-flash.
        if device.runtime.flash_encryption_detected is True:
            report.add_error(
                "This device was last read back as having Flash Encryption ENABLED, but this "
                "flash job has Flash Encryption turned off. An encrypted device generally "
                "refuses (or corrupts) a plaintext write. Enable Flash Encryption for this "
                "device below, or re-read its current state via Read Flash / eFuse / Chip Info "
                "if you believe this is stale."
            )
        return report

    if sec.enable_flash_encryption:
        if sec.key_source == "existing":
            if not sec.flash_encryption_key_path.strip():
                report.add_error("Flash Encryption is enabled but no key file has been selected.")
            elif not Path(sec.flash_encryption_key_path).is_file():
                report.add_error(f"Flash encryption key file not found: {sec.flash_encryption_key_path}")
            else:
                size = Path(sec.flash_encryption_key_path).stat().st_size
                if size not in expected_key_sizes_bytes():
                    report.add_warning(
                        f"Flash encryption key file is {size} bytes; typical AES-XTS keys for "
                        f"esptool/espefuse are {' or '.join(str(s) for s in expected_key_sizes_bytes())} "
                        "bytes. Double-check this is the correct key for this chip before burning it."
                    )
        if not is_legacy_efuse_chip(device.chip_type) and not sec.flash_encryption_key_block.strip():
            report.add_error("Select an eFuse key block to burn the flash encryption key into.")

    if sec.enable_secure_boot:
        if sec.key_source == "existing":
            if not sec.secure_boot_key_path.strip():
                report.add_error("Secure Boot is enabled but no signing key file has been selected.")
            elif not Path(sec.secure_boot_key_path).is_file():
                report.add_error(f"Secure boot key file not found: {sec.secure_boot_key_path}")
        if not is_legacy_efuse_chip(device.chip_type) and not sec.secure_boot_key_block.strip():
            report.add_error("Select an eFuse key block to burn the secure boot key digest into.")

    if device.chip_type == "auto" and (sec.enable_flash_encryption or sec.enable_secure_boot):
        report.add_error(
            "A specific chip must be selected (not \"auto\") before provisioning -- espefuse needs "
            "to know the exact target to pick the correct eFuse layout."
        )

    return report
