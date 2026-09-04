"""
Unit tests for app/models/device_model.py.

Pure dataclasses -- no Qt involved, so these run fast and without a
QApplication.
"""

from __future__ import annotations

from app.models.device_model import DeviceConfig, DeviceRuntimeState, SecurityConfig
from app.models.firmware_model import FirmwareEntry
from app.utilities.constants import DEFAULT_CHIP, STATUS_WAITING


# --------------------------------------------------------------------------
# SecurityConfig
# --------------------------------------------------------------------------
class TestSecurityConfig:
    def test_defaults(self):
        cfg = SecurityConfig()
        assert cfg.enable_flash_encryption is False
        assert cfg.enable_secure_boot is False
        assert cfg.encrypt_on_write is True

    def test_to_dict_from_dict_roundtrip(self):
        cfg = SecurityConfig(
            enable_flash_encryption=True,
            flash_encryption_mode="release",
            enable_secure_boot=True,
            secure_boot_version="2",
            secure_boot_scheme="ecdsa256",
            key_source="existing",
            flash_encryption_key_path="/keys/fe.bin",
            secure_boot_key_path="/keys/sb.pem",
            keep_key_readable=True,
            encrypt_on_write=False,
            custom_efuse_args="--do-not-confirm",
        )
        restored = SecurityConfig.from_dict(cfg.to_dict())
        assert restored == cfg

    def test_from_dict_missing_keys_uses_defaults(self):
        restored = SecurityConfig.from_dict({})
        assert restored == SecurityConfig()

    def test_from_dict_ignores_unknown_keys(self):
        data = SecurityConfig().to_dict()
        data["totally_unknown_future_field"] = "surprise"
        restored = SecurityConfig.from_dict(data)
        assert restored == SecurityConfig()

    def test_clone_is_independent_copy(self):
        cfg = SecurityConfig(enable_flash_encryption=True)
        clone = cfg.clone()
        assert clone == cfg
        clone.enable_flash_encryption = False
        assert cfg.enable_flash_encryption is True


# --------------------------------------------------------------------------
# DeviceRuntimeState
# --------------------------------------------------------------------------
class TestDeviceRuntimeState:
    def test_defaults(self):
        state = DeviceRuntimeState()
        assert state.status == STATUS_WAITING
        assert state.progress_percent == 0
        assert state.connected is False
        assert state.flash_encryption_detected is None
        assert state.secure_boot_detected is None
        assert state.log_lines == []

    def test_log_lines_default_factory_is_not_shared(self):
        """Each instance must get its own list -- a classic dataclass
        mutable-default footgun that `field(default_factory=list)` guards
        against; verify it actually does."""
        a = DeviceRuntimeState()
        b = DeviceRuntimeState()
        a.log_lines.append("line 1")
        assert b.log_lines == []


# --------------------------------------------------------------------------
# DeviceConfig -- firmware list operations
# --------------------------------------------------------------------------
class TestDeviceConfigFirmwareOps:
    def _firmware(self, name="firmware.bin", address="0x10000", enabled=True) -> FirmwareEntry:
        return FirmwareEntry(file_path=f"/tmp/{name}", address=address, enabled=enabled)

    def test_add_firmware(self):
        device = DeviceConfig()
        entry = self._firmware()
        device.add_firmware(entry)
        assert device.firmware == [entry]

    def test_remove_firmware(self):
        device = DeviceConfig()
        keep = self._firmware("keep.bin", "0x1000")
        drop = self._firmware("drop.bin", "0x8000")
        device.add_firmware(keep)
        device.add_firmware(drop)
        device.remove_firmware(drop.id)
        assert device.firmware == [keep]

    def test_remove_firmware_unknown_id_is_noop(self):
        device = DeviceConfig()
        entry = self._firmware()
        device.add_firmware(entry)
        device.remove_firmware("does-not-exist")
        assert device.firmware == [entry]

    def test_move_firmware_up(self):
        device = DeviceConfig()
        first = self._firmware("a.bin", "0x1000")
        second = self._firmware("b.bin", "0x8000")
        device.add_firmware(first)
        device.add_firmware(second)
        device.move_firmware(second.id, -1)
        assert [f.id for f in device.firmware] == [second.id, first.id]

    def test_move_firmware_down(self):
        device = DeviceConfig()
        first = self._firmware("a.bin", "0x1000")
        second = self._firmware("b.bin", "0x8000")
        device.add_firmware(first)
        device.add_firmware(second)
        device.move_firmware(first.id, 1)
        assert [f.id for f in device.firmware] == [second.id, first.id]

    def test_move_firmware_out_of_bounds_is_noop(self):
        device = DeviceConfig()
        only = self._firmware()
        device.add_firmware(only)
        device.move_firmware(only.id, -1)  # already first, moving up is a no-op
        device.move_firmware(only.id, 1)  # already last, moving down is a no-op
        assert device.firmware == [only]

    def test_move_firmware_unknown_id_is_noop(self):
        device = DeviceConfig()
        only = self._firmware()
        device.add_firmware(only)
        device.move_firmware("nope", 1)
        assert device.firmware == [only]

    def test_duplicate_firmware_inserts_after_original_with_new_id(self):
        device = DeviceConfig()
        first = self._firmware("a.bin", "0x1000")
        second = self._firmware("b.bin", "0x8000")
        device.add_firmware(first)
        device.add_firmware(second)
        device.duplicate_firmware(first.id)
        assert len(device.firmware) == 3
        assert device.firmware[0].id == first.id
        duplicate = device.firmware[1]
        assert duplicate.id != first.id
        assert duplicate.file_path == first.file_path
        assert device.firmware[2].id == second.id

    def test_duplicate_firmware_unknown_id_is_noop(self):
        device = DeviceConfig()
        only = self._firmware()
        device.add_firmware(only)
        device.duplicate_firmware("nope")
        assert len(device.firmware) == 1

    def test_enabled_firmware_filters_disabled_entries(self):
        device = DeviceConfig()
        enabled = self._firmware("on.bin", "0x1000", enabled=True)
        disabled = self._firmware("off.bin", "0x8000", enabled=False)
        device.add_firmware(enabled)
        device.add_firmware(disabled)
        assert device.enabled_firmware() == [enabled]


# --------------------------------------------------------------------------
# DeviceConfig -- clone
# --------------------------------------------------------------------------
class TestDeviceConfigClone:
    def test_clone_gets_new_id_and_default_name_suffix(self):
        original = DeviceConfig(name="Line A #1", com_port="COM3")
        clone = original.clone()
        assert clone.id != original.id
        assert clone.name == "Line A #1 (Copy)"

    def test_clone_custom_name(self):
        original = DeviceConfig(name="Line A #1")
        clone = original.clone(new_name="Line A #2")
        assert clone.name == "Line A #2"

    def test_clone_does_not_copy_com_port(self):
        original = DeviceConfig(com_port="COM5")
        clone = original.clone()
        assert clone.com_port == ""

    def test_clone_copies_settings_and_tags(self):
        original = DeviceConfig(chip_type="esp32s3", baud_rate=921600)
        original.tags = ["Line A", "Batch 7"]
        clone = original.clone()
        assert clone.chip_type == "esp32s3"
        assert clone.baud_rate == 921600
        assert clone.tags == ["Line A", "Batch 7"]
        # Mutating the clone's tags must not affect the original.
        clone.tags.append("extra")
        assert "extra" not in original.tags

    def test_clone_deep_copies_firmware_list(self):
        original = DeviceConfig()
        original.add_firmware(FirmwareEntry(file_path="/tmp/fw.bin", address="0x10000"))
        clone = original.clone()
        assert len(clone.firmware) == 1
        assert clone.firmware[0].id != original.firmware[0].id
        clone.firmware[0].address = "0x20000"
        assert original.firmware[0].address == "0x10000"

    def test_clone_with_generated_key_source_does_not_copy_key_paths(self):
        original = DeviceConfig()
        original.security.key_source = "generate"
        original.security.flash_encryption_key_path = "/keys/original_fe.bin"
        original.security.secure_boot_key_path = "/keys/original_sb.pem"
        clone = original.clone()
        assert clone.security.flash_encryption_key_path == ""
        assert clone.security.secure_boot_key_path == ""

    def test_clone_with_existing_key_source_copies_key_paths(self):
        original = DeviceConfig()
        original.security.key_source = "existing"
        original.security.flash_encryption_key_path = "/keys/shared_fe.bin"
        clone = original.clone()
        assert clone.security.flash_encryption_key_path == "/keys/shared_fe.bin"

    def test_clone_security_is_independent(self):
        original = DeviceConfig()
        clone = original.clone()
        clone.security.enable_secure_boot = True
        assert original.security.enable_secure_boot is False


# --------------------------------------------------------------------------
# DeviceConfig -- serialization
# --------------------------------------------------------------------------
class TestDeviceConfigSerialization:
    def test_to_dict_from_dict_roundtrip(self):
        device = DeviceConfig(name="Bench 1", com_port="COM4", chip_type="esp32c3")
        device.add_firmware(FirmwareEntry(file_path="/tmp/bootloader.bin", address="0x1000"))
        device.tags = ["batch-7"]
        device.security.enable_flash_encryption = True

        restored = DeviceConfig.from_dict(device.to_dict())

        assert restored.id == device.id
        assert restored.name == device.name
        assert restored.com_port == device.com_port
        assert restored.chip_type == device.chip_type
        assert restored.tags == device.tags
        assert len(restored.firmware) == 1
        assert restored.firmware[0].file_name == "bootloader.bin"
        assert restored.security.enable_flash_encryption is True

    def test_to_dict_excludes_runtime_state(self):
        device = DeviceConfig()
        device.runtime.progress_percent = 55
        device.runtime.status = "Flashing"
        assert "runtime" not in device.to_dict()

    def test_from_dict_missing_fields_uses_defaults(self):
        restored = DeviceConfig.from_dict({"name": "Minimal"})
        assert restored.name == "Minimal"
        assert restored.chip_type == DEFAULT_CHIP
        assert restored.firmware == []
        assert restored.tags == []

    def test_from_dict_empty_dict(self):
        restored = DeviceConfig.from_dict({})
        assert isinstance(restored, DeviceConfig)
        assert restored.firmware == []

    def test_from_dict_generates_id_when_missing(self):
        a = DeviceConfig.from_dict({"name": "A"})
        b = DeviceConfig.from_dict({"name": "B"})
        assert a.id != b.id
