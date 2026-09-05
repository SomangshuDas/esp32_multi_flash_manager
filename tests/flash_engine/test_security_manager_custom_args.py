"""
Unit tests for the custom-eFuse-args validation guard consolidated into
app/flash_engine/security_manager.py's SecurityCommandBuilder (see
_custom_efuse_args_tokens).
"""

from __future__ import annotations

import pytest

from app.flash_engine.security_manager import SecurityCommandBuilder
from app.models.device_model import DeviceConfig, SecurityConfig
from app.utilities.constants import SUPPORTED_CHIPS


def _device(custom_efuse_args: str = "") -> DeviceConfig:
    device = DeviceConfig(name="Device", com_port="COM3", chip_type=SUPPORTED_CHIPS[0])
    device.security = SecurityConfig(
        flash_encryption_key_path="/tmp/key.bin",
        custom_efuse_args=custom_efuse_args,
    )
    return device


class TestCustomEfuseArgsGuard:
    def test_empty_custom_args_build_normally(self):
        args = SecurityCommandBuilder.build_burn_flash_encryption_key_args(_device(""))
        assert "burn-key" in args

    def test_safe_custom_args_are_appended(self):
        args = SecurityCommandBuilder.build_burn_flash_encryption_key_args(_device("--force-write-always"))
        assert "--force-write-always" in args

    def test_blocked_flag_raises_value_error(self):
        with pytest.raises(ValueError, match="custom eFuse arguments are invalid"):
            SecurityCommandBuilder.build_burn_flash_encryption_key_args(_device("--port /dev/ttyFAKE"))

    def test_second_burn_subcommand_is_blocked(self):
        with pytest.raises(ValueError):
            SecurityCommandBuilder.build_burn_flash_encryption_key_args(_device("burn-key"))

    def test_path_like_token_is_blocked(self):
        with pytest.raises(ValueError):
            SecurityCommandBuilder.build_burn_flash_encryption_key_args(_device("../../etc/passwd"))

    def test_guard_also_applies_to_secure_boot_key_burn(self):
        device = _device("--port /dev/ttyFAKE")
        device.security.secure_boot_key_path = "/tmp/sb.bin"
        with pytest.raises(ValueError):
            SecurityCommandBuilder.build_burn_secure_boot_key_args(device)
