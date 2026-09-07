"""
Tests for MainWindow._confirm_legacy_migration_before_proceeding -- the
forced-save guard described in docs/USER_MANUAL.md "Forced save for
legacy projects": a project opened from the legacy `.efmproj` format and
never yet Saved As to `.emfm` must be saved (or the action cancelled)
before New Project, Open Project, or closing the app -- unlike the
ordinary unsaved-changes prompt, there's no "discard" option, since
discarding here would mean this specific file quietly never migrates.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QMessageBox


class TestLegacyMigrationGuard:
    def test_returns_true_immediately_when_nothing_pending(self, main_window):
        window = main_window
        assert window.project_controller.legacy_pending_migration is False
        assert window._confirm_legacy_migration_before_proceeding() is True

    def test_cancel_blocks_and_leaves_project_pending(self, main_window):
        window = main_window
        window.project_controller.legacy_pending_migration = True

        with patch("app.ui.main_window.QMessageBox.warning", return_value=QMessageBox.StandardButton.Cancel):
            result = window._confirm_legacy_migration_before_proceeding()

        assert result is False
        assert window.project_controller.legacy_pending_migration is True

    def test_choosing_save_invokes_save_as_and_clears_pending_on_success(self, main_window):
        window = main_window
        window.project_controller.legacy_pending_migration = True

        def fake_save_as():
            window.project_controller.legacy_pending_migration = False

        with patch("app.ui.main_window.QMessageBox.warning", return_value=QMessageBox.StandardButton.Save), \
             patch.object(window, "_on_save_project_as", side_effect=fake_save_as) as mock_save_as:
            result = window._confirm_legacy_migration_before_proceeding()

        mock_save_as.assert_called_once()
        assert result is True
        assert window.project_controller.legacy_pending_migration is False

    def test_cancelling_the_save_as_dialog_itself_leaves_pending_and_returns_false(self, main_window):
        """User chooses "Save" on the warning, but then cancels the actual
        Save As file dialog (_on_save_project_as no-ops in that case)."""
        window = main_window
        window.project_controller.legacy_pending_migration = True

        with patch("app.ui.main_window.QMessageBox.warning", return_value=QMessageBox.StandardButton.Save), \
             patch.object(window, "_on_save_project_as"):
            result = window._confirm_legacy_migration_before_proceeding()

        assert result is False
        assert window.project_controller.legacy_pending_migration is True


class TestLegacyMigrationGuardWiredIntoLifecycle:
    def test_new_project_blocked_while_migration_pending(self, main_window):
        window = main_window
        window.project_controller.legacy_pending_migration = True

        with patch.object(window, "_confirm_legacy_migration_before_proceeding", return_value=False), \
             patch.object(window.project_controller, "new_project") as mock_new:
            window._on_new_project()

        mock_new.assert_not_called()

    def test_open_project_blocked_while_migration_pending(self, main_window):
        window = main_window
        window.project_controller.legacy_pending_migration = True

        with patch.object(window, "_confirm_legacy_migration_before_proceeding", return_value=False), \
             patch.object(window.project_controller, "open_project") as mock_open:
            window._on_open_project("/some/path.emfm")

        mock_open.assert_not_called()

    def test_close_event_blocked_while_migration_pending(self, main_window):
        window = main_window
        window.project_controller.legacy_pending_migration = True
        event = MagicMock()

        with patch.object(window, "_confirm_legacy_migration_before_proceeding", return_value=False):
            window.closeEvent(event)

        event.ignore.assert_called_once()
        event.accept.assert_not_called()
