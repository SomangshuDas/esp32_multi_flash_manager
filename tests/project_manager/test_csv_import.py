"""
Tests for app/project_manager/csv_import.py: bulk device import from CSV
(Devices -> Import Devices from CSV...).
"""

from __future__ import annotations

import pytest

from app.project_manager.csv_import import import_devices_from_csv
from app.utilities.constants import DEFAULT_BAUD, DEFAULT_CHIP


def _write_csv(tmp_path, content: str, name: str = "devices.csv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestBasicImport:
    def test_imports_all_recognized_columns(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "name,com_port,chip_type,baud_rate,tags\n"
            "Device 1,COM5,esp32s3,921600,Line A;RFID\n"
            "Device 2,/dev/ttyUSB0,esp32,115200,\n",
        )
        result = import_devices_from_csv(path)
        assert result.imported_count == 2
        assert result.errors == []

        d1, d2 = result.devices
        assert d1.name == "Device 1"
        assert d1.com_port == "COM5"
        assert d1.chip_type == "esp32s3"
        assert d1.baud_rate == 921600
        assert d1.tags == ["Line A", "RFID"]

        assert d2.name == "Device 2"
        assert d2.tags == []

    def test_only_name_column_required(self, tmp_path):
        path = _write_csv(tmp_path, "name\nDevice 1\nDevice 2\n")
        result = import_devices_from_csv(path)
        assert result.imported_count == 2
        assert result.devices[0].chip_type == DEFAULT_CHIP
        assert result.devices[0].baud_rate == DEFAULT_BAUD

    def test_column_names_are_case_insensitive(self, tmp_path):
        path = _write_csv(tmp_path, "NAME,COM_PORT\nDevice 1,COM3\n")
        result = import_devices_from_csv(path)
        assert result.imported_count == 1
        assert result.devices[0].com_port == "COM3"

    def test_unknown_extra_columns_are_ignored(self, tmp_path):
        path = _write_csv(tmp_path, "name,notes,operator\nDevice 1,fine,Alice\n")
        result = import_devices_from_csv(path)
        assert result.imported_count == 1
        assert result.errors == []

    def test_bom_prefixed_file_is_handled(self, tmp_path):
        path = tmp_path / "devices.csv"
        path.write_bytes("\ufeffname\nDevice 1\n".encode("utf-8"))
        result = import_devices_from_csv(path)
        assert result.imported_count == 1
        assert result.devices[0].name == "Device 1"


class TestErrorHandling:
    def test_missing_name_column_entirely(self, tmp_path):
        path = _write_csv(tmp_path, "com_port\nCOM5\n")
        result = import_devices_from_csv(path)
        assert result.imported_count == 0
        assert any("name" in e for e in result.errors)

    def test_row_missing_name_value_is_skipped_not_fatal(self, tmp_path):
        path = _write_csv(tmp_path, "name,com_port\n,COM5\nDevice 2,COM6\n")
        result = import_devices_from_csv(path)
        assert result.imported_count == 1
        assert result.devices[0].name == "Device 2"
        assert len(result.errors) == 1
        assert "Row 1" in result.errors[0]

    def test_invalid_baud_rate_is_skipped_not_fatal(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "name,baud_rate\nDevice 1,not-a-number\nDevice 2,115200\n",
        )
        result = import_devices_from_csv(path)
        assert result.imported_count == 1
        assert result.devices[0].name == "Device 2"
        assert len(result.errors) == 1
        assert "baud_rate" in result.errors[0]

    def test_empty_file_has_no_header_error(self, tmp_path):
        path = _write_csv(tmp_path, "")
        result = import_devices_from_csv(path)
        assert result.imported_count == 0
        assert result.errors
