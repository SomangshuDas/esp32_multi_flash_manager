"""Unit tests for app/models/history_model.py."""

from __future__ import annotations

import csv

from app.models.history_model import HistoryEntry, export_history_csv
from app.utilities.constants import QC_STATUS_NOT_TESTED


class TestHistoryEntryCreate:
    def test_create_splits_timestamp_into_date_and_time(self):
        entry = HistoryEntry.create(
            device_name="Bench 1", com_port="COM3", firmware_summary="firmware.bin @ 0x10000",
            duration_seconds=12.345, result="Completed",
        )
        assert entry.date
        assert entry.time
        assert entry.device_name == "Bench 1"
        assert entry.com_port == "COM3"
        assert entry.result == "Completed"

    def test_create_rounds_duration(self):
        entry = HistoryEntry.create(
            device_name="d", com_port="COM1", firmware_summary="fw", duration_seconds=1.2649, result="Completed",
        )
        assert entry.duration_seconds == 1.3

    def test_create_defaults_qc_status_not_tested(self):
        entry = HistoryEntry.create(
            device_name="d", com_port="COM1", firmware_summary="fw", duration_seconds=1.0, result="Completed",
        )
        assert entry.qc_status == QC_STATUS_NOT_TESTED

    def test_create_generates_unique_ids(self):
        a = HistoryEntry.create(device_name="d", com_port="COM1", firmware_summary="fw", duration_seconds=1.0, result="Completed")
        b = HistoryEntry.create(device_name="d", com_port="COM1", firmware_summary="fw", duration_seconds=1.0, result="Completed")
        assert a.id != b.id

    def test_create_stores_device_id_and_mac(self):
        entry = HistoryEntry.create(
            device_name="d", com_port="COM1", firmware_summary="fw", duration_seconds=1.0, result="Completed",
            device_id="dev-123", mac_address="AA:BB:CC:DD:EE:FF",
        )
        assert entry.device_id == "dev-123"
        assert entry.mac_address == "AA:BB:CC:DD:EE:FF"


class TestHistoryEntrySerialization:
    def _entry(self) -> HistoryEntry:
        return HistoryEntry.create(
            device_name="Bench 1", com_port="COM3", firmware_summary="firmware.bin @ 0x10000",
            duration_seconds=5.0, result="Completed", device_id="dev-1", mac_address="11:22:33:44:55:66",
        )

    def test_to_dict_from_dict_roundtrip(self):
        entry = self._entry()
        restored = HistoryEntry.from_dict(entry.to_dict())
        assert restored == entry

    def test_from_dict_ignores_unknown_future_keys(self):
        data = self._entry().to_dict()
        data["some_field_added_in_a_future_version"] = "ignored"
        # Must not raise TypeError for an unexpected keyword argument.
        restored = HistoryEntry.from_dict(data)
        assert restored.device_name == "Bench 1"

    def test_from_dict_missing_optional_fields_uses_defaults(self):
        minimal = {
            "date": "2026-01-01", "time": "12:00:00", "device_name": "d",
            "com_port": "COM1", "firmware_summary": "fw", "duration_seconds": 1.0,
            "result": "Completed",
        }
        restored = HistoryEntry.from_dict(minimal)
        assert restored.qc_status == QC_STATUS_NOT_TESTED
        assert restored.device_id == ""
        assert restored.mac_address == ""


class TestExportHistoryCsv:
    def test_export_writes_header_and_rows(self, tmp_path):
        entries = [
            HistoryEntry.create(device_name="Bench 1", com_port="COM3", firmware_summary="fw1", duration_seconds=5.0, result="Completed"),
            HistoryEntry.create(device_name="Bench 2", com_port="COM4", firmware_summary="fw2", duration_seconds=3.2, result="Failed"),
        ]
        destination = tmp_path / "history.csv"
        export_history_csv(entries, str(destination))

        with destination.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        assert len(rows) == 2
        assert rows[0]["device_name"] == "Bench 1"
        assert rows[0]["result"] == "Completed"
        assert rows[1]["device_name"] == "Bench 2"
        assert rows[1]["result"] == "Failed"

    def test_export_empty_list_writes_header_only(self, tmp_path):
        destination = tmp_path / "empty.csv"
        export_history_csv([], str(destination))
        with destination.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows == []

    def test_export_field_order_matches_expected_columns(self, tmp_path):
        destination = tmp_path / "order.csv"
        export_history_csv([], str(destination))
        with destination.open(newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        assert header == [
            "date", "time", "device_name", "com_port", "mac_address",
            "firmware_summary", "duration_seconds", "result", "qc_status",
        ]
