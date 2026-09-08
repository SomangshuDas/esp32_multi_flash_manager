"""
Tests for app/utilities/diagnostics.py: the one-click "Export Diagnostics
Bundle" feature.
"""

from __future__ import annotations

import json
import zipfile

from app.utilities.constants import APP_VERSION
from app.utilities.diagnostics import collect_diagnostics_info, export_diagnostics_bundle


def _make_log_dir(tmp_path, filenames):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for name in filenames:
        (log_dir / name).write_text(f"contents of {name}\n", encoding="utf-8")
    return log_dir


class TestCollectDiagnosticsInfo:
    def test_reports_app_version(self, tmp_path):
        log_dir = _make_log_dir(tmp_path, ["application.log"])
        info = collect_diagnostics_info(log_dir)
        assert info.app_version == APP_VERSION

    def test_only_lists_logs_that_exist(self, tmp_path):
        log_dir = _make_log_dir(tmp_path, ["application.log", "error.log"])
        info = collect_diagnostics_info(log_dir)
        assert info.included_logs == ["application.log", "error.log"]

    def test_no_logs_present_is_not_an_error(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        info = collect_diagnostics_info(log_dir)
        assert info.included_logs == []


class TestExportDiagnosticsBundle:
    def test_bundle_contains_manifest_and_logs(self, tmp_path):
        log_dir = _make_log_dir(tmp_path, ["application.log", "flash.log", "error.log", "debug.log"])
        dest = tmp_path / "bundle.zip"
        export_diagnostics_bundle(dest, log_dir=log_dir)

        assert dest.is_file()
        with zipfile.ZipFile(dest) as bundle:
            names = bundle.namelist()
            assert "diagnostics_info.json" in names
            for expected in ("logs/application.log", "logs/flash.log", "logs/error.log", "logs/debug.log"):
                assert expected in names
            manifest = json.loads(bundle.read("diagnostics_info.json"))
            assert manifest["app_version"] == APP_VERSION
            assert set(manifest["included_logs"]) == {
                "application.log", "flash.log", "error.log", "debug.log",
            }

    def test_missing_log_files_are_skipped_not_fatal(self, tmp_path):
        log_dir = _make_log_dir(tmp_path, ["application.log"])  # only one of four
        dest = tmp_path / "bundle.zip"
        export_diagnostics_bundle(dest, log_dir=log_dir)
        with zipfile.ZipFile(dest) as bundle:
            assert "logs/application.log" in bundle.namelist()
            assert "logs/flash.log" not in bundle.namelist()

    def test_creates_parent_directories(self, tmp_path):
        log_dir = _make_log_dir(tmp_path, ["application.log"])
        dest = tmp_path / "nested" / "dir" / "bundle.zip"
        export_diagnostics_bundle(dest, log_dir=log_dir)
        assert dest.is_file()
