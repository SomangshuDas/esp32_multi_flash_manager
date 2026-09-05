"""
Unit tests for the custom-args validation guard added to
app/flash_engine/esptool_wrapper.py's FlashCommandBuilder.
"""

from __future__ import annotations

import pytest

from app.flash_engine.esptool_wrapper import FlashCommandBuilder
from app.models.device_model import DeviceConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import FLASH_MODES, SUPPORTED_CHIPS


def _device(custom_flash_args: str = "") -> DeviceConfig:
    device = DeviceConfig(
        name="Device", com_port="COM3",
        chip_type=SUPPORTED_CHIPS[0], flash_mode=FLASH_MODES[0],
        custom_flash_args=custom_flash_args,
    )
    entry = FirmwareEntry(file_path="/tmp/app.bin", address="0x10000", enabled=True)
    entry.file_size = 0x1000
    device.add_firmware(entry)
    return device


class TestCustomFlashArgsGuard:
    def test_empty_custom_args_build_normally(self):
        args = FlashCommandBuilder.build_write_flash_args(_device(""))
        assert "0x10000" in args

    def test_safe_custom_args_are_appended(self):
        args = FlashCommandBuilder.build_write_flash_args(_device("--no-progress"))
        assert "--no-progress" in args

    def test_quoted_custom_args_are_split_correctly(self):
        # shlex.split (not a naive .split()) so a quoted value with a
        # space in it stays as one token.
        args = FlashCommandBuilder.build_write_flash_args(_device('--extra-note "hard reset"'))
        assert "hard reset" in args

    def test_blocked_flag_raises_value_error(self):
        with pytest.raises(ValueError, match="custom flash arguments are invalid"):
            FlashCommandBuilder.build_write_flash_args(_device("--port /dev/ttyFAKE"))

    def test_path_like_token_raises_value_error(self):
        with pytest.raises(ValueError):
            FlashCommandBuilder.build_write_flash_args(_device("../../etc/passwd"))
