"""
Tests for app/ui/validation_dialog.py's dry-run framing -- see
ROADMAP.md's "Dry-run / pre-flight simulation mode" entry. A dry-run
report is purely informational (it isn't gating an Upload click), so the
dialog must always show a single Close button regardless of whether
errors were found, and use dry-run-specific title/note text.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialogButtonBox

from app.flash_engine.validator import ValidationReport
from app.ui.validation_dialog import ValidationReportDialog


class TestDryRunFraming:
    def test_dry_run_report_shows_dry_run_title(self, qtbot):
        report = ValidationReport(dry_run=True)
        dialog = ValidationReportDialog(report)
        qtbot.addWidget(dialog)
        assert "Dry Run" in dialog.windowTitle()

    def test_dry_run_with_errors_shows_close_only(self, qtbot):
        report = ValidationReport(dry_run=True)
        report.add_error("Device A", "Something is wrong")
        dialog = ValidationReportDialog(report)
        qtbot.addWidget(dialog)
        buttons = dialog.findChild(QDialogButtonBox)
        standard_buttons = buttons.standardButtons()
        assert standard_buttons == QDialogButtonBox.StandardButton.Close

    def test_dry_run_with_no_errors_still_shows_close_only(self, qtbot):
        """Unlike a real pre-upload report, a clean dry-run result must
        NOT offer a "Proceed With Upload" button -- there's no upload to
        proceed with."""
        report = ValidationReport(dry_run=True)
        dialog = ValidationReportDialog(report)
        qtbot.addWidget(dialog)
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons.standardButtons() == QDialogButtonBox.StandardButton.Close

    def test_non_dry_run_report_uses_normal_title(self, qtbot):
        report = ValidationReport(dry_run=False)
        dialog = ValidationReportDialog(report)
        qtbot.addWidget(dialog)
        assert "Pre-Upload" in dialog.windowTitle()

    def test_non_dry_run_with_errors_shows_ok_only(self, qtbot):
        report = ValidationReport(dry_run=False)
        report.add_error("Device A", "Something is wrong")
        dialog = ValidationReportDialog(report)
        qtbot.addWidget(dialog)
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons.standardButtons() == QDialogButtonBox.StandardButton.Ok

    def test_non_dry_run_with_no_errors_offers_proceed_and_cancel(self, qtbot):
        report = ValidationReport(dry_run=False)
        dialog = ValidationReportDialog(report)
        qtbot.addWidget(dialog)
        buttons = dialog.findChild(QDialogButtonBox)
        expected = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        assert buttons.standardButtons() == expected

    def test_explicit_dry_run_override_wins_over_report_flag(self, qtbot):
        """Passing dry_run explicitly to the dialog overrides
        report.dry_run -- lets a caller reuse a report object across both
        framings if it ever needs to."""
        report = ValidationReport(dry_run=False)
        dialog = ValidationReportDialog(report, dry_run=True)
        qtbot.addWidget(dialog)
        assert "Dry Run" in dialog.windowTitle()
