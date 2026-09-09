"""
Tests for app/project_manager/zip_manifest_import.py -- zip + manifest
bulk-flashing import. See ROADMAP.md's corresponding entry and the
module's own docstring for the manifest CSV format.
"""

from __future__ import annotations

import zipfile

import pytest

from app.project_manager.zip_manifest_import import (
    ZipManifestImportError,
    import_devices_from_zip_bundle,
)


def _make_bundle(tmp_path, manifest_text: str, files: dict[str, bytes], name: str = "bundle.zip") -> str:
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.csv", manifest_text)
        for filename, content in files.items():
            archive.writestr(filename, content)
    return str(zip_path)


class TestBasicImport:
    def test_single_device_single_firmware_file(self, tmp_path):
        manifest = "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})

        result = import_devices_from_zip_bundle(bundle)

        assert result.imported_count == 1
        assert result.errors == []
        device = result.devices[0]
        assert device.name == "Bench 1"
        assert len(device.firmware) == 1
        assert device.firmware[0].address == "0x10000"
        assert device.firmware[0].file_name == "firmware.bin"

    def test_multiple_rows_same_device_produce_multiple_firmware_entries(self, tmp_path):
        manifest = (
            "device_name,firmware_file,address\n"
            "Bench 1,bootloader.bin,0x1000\n"
            "Bench 1,firmware.bin,0x10000\n"
        )
        bundle = _make_bundle(
            tmp_path, manifest, {"bootloader.bin": b"\x00" * 16, "firmware.bin": b"\x00" * 64},
        )

        result = import_devices_from_zip_bundle(bundle)

        assert result.imported_count == 1
        device = result.devices[0]
        assert len(device.firmware) == 2
        addresses = {e.address for e in device.firmware}
        assert addresses == {"0x1000", "0x10000"}

    def test_multiple_devices(self, tmp_path):
        manifest = (
            "device_name,firmware_file,address\n"
            "Bench 1,firmware.bin,0x10000\n"
            "Bench 2,firmware.bin,0x10000\n"
        )
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})

        result = import_devices_from_zip_bundle(bundle)

        assert result.imported_count == 2
        assert {d.name for d in result.devices} == {"Bench 1", "Bench 2"}

    def test_firmware_file_in_subfolder_is_resolved(self, tmp_path):
        manifest = "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n"
        bundle_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(bundle_path, "w") as archive:
            archive.writestr("manifest.csv", manifest)
            archive.writestr("binaries/firmware.bin", b"\x00" * 64)

        result = import_devices_from_zip_bundle(str(bundle_path))
        assert result.imported_count == 1
        assert result.devices[0].firmware[0].file_name == "firmware.bin"

    def test_manifest_in_top_level_folder_is_found(self, tmp_path):
        manifest = "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n"
        bundle_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(bundle_path, "w") as archive:
            archive.writestr("release_v1/manifest.csv", manifest)
            archive.writestr("release_v1/firmware.bin", b"\x00" * 64)

        result = import_devices_from_zip_bundle(str(bundle_path))
        assert result.imported_count == 1


class TestOptionalColumns:
    def test_tags_are_split_on_semicolon(self, tmp_path):
        manifest = 'device_name,tags,firmware_file,address\nBench 1,"Line A;RFID Batch",firmware.bin,0x10000\n'
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert set(result.devices[0].tags) == {"Line A", "RFID Batch"}

    def test_chip_type_defaults_when_blank(self, tmp_path):
        from app.utilities.constants import DEFAULT_CHIP

        manifest = "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert result.devices[0].chip_type == DEFAULT_CHIP

    def test_chip_type_from_manifest_is_applied(self, tmp_path):
        manifest = "device_name,chip_type,firmware_file,address\nBench 1,esp32s3,firmware.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert result.devices[0].chip_type == "esp32s3"

    def test_address_falls_back_to_known_firmware_address(self, tmp_path):
        manifest = "device_name,firmware_file\nBench 1,bootloader.bin\n"
        bundle = _make_bundle(tmp_path, manifest, {"bootloader.bin": b"\x00" * 16})
        result = import_devices_from_zip_bundle(bundle)
        assert result.devices[0].firmware[0].address == "0x1000"

    def test_address_falls_back_to_placeholder_for_unrecognized_filename(self, tmp_path):
        manifest = "device_name,firmware_file\nBench 1,mystery.bin\n"
        bundle = _make_bundle(tmp_path, manifest, {"mystery.bin": b"\x00" * 16})
        result = import_devices_from_zip_bundle(bundle)
        assert result.devices[0].firmware[0].address == "0x0"

    def test_enabled_false_is_respected(self, tmp_path):
        manifest = "device_name,firmware_file,address,enabled\nBench 1,firmware.bin,0x10000,false\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert result.devices[0].firmware[0].enabled is False

    def test_enabled_defaults_true_when_blank(self, tmp_path):
        manifest = "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert result.devices[0].firmware[0].enabled is True


class TestRowErrors:
    def test_missing_device_name_is_a_row_error_not_a_fatal_failure(self, tmp_path):
        manifest = "device_name,firmware_file,address\n,firmware.bin,0x10000\nBench 1,firmware.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert result.imported_count == 1
        assert len(result.errors) == 1

    def test_missing_firmware_file_column_is_a_row_error(self, tmp_path):
        manifest = "device_name,firmware_file,address\nBench 1,,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {})
        result = import_devices_from_zip_bundle(bundle)
        assert result.imported_count == 0
        assert len(result.errors) == 1

    def test_firmware_file_not_in_bundle_is_a_row_error(self, tmp_path):
        manifest = "device_name,firmware_file,address\nBench 1,does_not_exist.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {})
        result = import_devices_from_zip_bundle(bundle)
        assert result.imported_count == 0
        assert len(result.errors) == 1
        assert "does_not_exist.bin" in result.errors[0]


class TestArchiveLevelErrors:
    def test_missing_zip_file_raises(self, tmp_path):
        with pytest.raises(ZipManifestImportError):
            import_devices_from_zip_bundle(str(tmp_path / "does_not_exist.zip"))

    def test_not_a_zip_file_raises(self, tmp_path):
        bogus = tmp_path / "not_a_zip.zip"
        bogus.write_text("this is not a zip file")
        with pytest.raises(ZipManifestImportError):
            import_devices_from_zip_bundle(str(bogus))

    def test_missing_manifest_raises(self, tmp_path):
        zip_path = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("firmware.bin", b"\x00" * 64)
        with pytest.raises(ZipManifestImportError):
            import_devices_from_zip_bundle(str(zip_path))

    def test_oversized_bundle_raises(self, tmp_path, monkeypatch):
        import app.project_manager.zip_manifest_import as module

        monkeypatch.setattr(module, "MAX_ZIP_BUNDLE_SIZE_BYTES", 10)
        manifest = "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n"
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        with pytest.raises(ZipManifestImportError):
            import_devices_from_zip_bundle(bundle)

    def test_zip_slip_entry_is_refused(self, tmp_path):
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("manifest.csv", "device_name,firmware_file,address\nBench 1,firmware.bin,0x10000\n")
            # A path-traversal entry name -- must never be extracted outside
            # the bundle's own extraction directory.
            archive.writestr("../../evil.bin", b"malicious")
        with pytest.raises(ZipManifestImportError):
            import_devices_from_zip_bundle(str(zip_path))


class TestRowCap:
    def test_manifest_row_cap_is_enforced(self, tmp_path, monkeypatch):
        import app.project_manager.zip_manifest_import as module

        monkeypatch.setattr(module, "MAX_ZIP_MANIFEST_ROWS", 2)
        manifest = "device_name,firmware_file,address\n" + "".join(
            f"Bench {i},firmware.bin,0x10000\n" for i in range(5)
        )
        bundle = _make_bundle(tmp_path, manifest, {"firmware.bin": b"\x00" * 64})
        result = import_devices_from_zip_bundle(bundle)
        assert result.imported_count == 2
        assert any("exceeds the maximum" in e for e in result.errors)
