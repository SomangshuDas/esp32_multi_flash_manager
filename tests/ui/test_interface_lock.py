"""
Tests for Interface Lock (Settings Lock vs Full Lock) in app/ui/main_window.py.

Settings Lock: the window stays usable (uploads, Serial Monitor, live
logs) but controls that change WHAT gets flashed and WHERE are disabled
-- Batch Edit, Firmware Profiles, Assign Firmware Set, the Firmware /
Device Settings / Security panels, and deleting devices.

Full Lock: the entire window (menu bar, central widget, docks, toolbars,
every action) is disabled behind a modal LockOverlay until the correct
key is entered.
"""

from __future__ import annotations

from app.utilities.constants import SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH


def _set_lock_key(window, key: str) -> None:
    """Bypass the QInputDialog prompt and store the key hash directly,
    exactly as _on_set_lock_key would after a successful entry."""
    window.settings.setValue(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH, window._hash_lock_key(key))


class TestSettingsLockBlocksDocumentedActions:
    def test_locking_disables_batch_edit_profiles_and_assign_firmware_actions(self, main_window):
        window = main_window
        _set_lock_key(window, "secret123")
        window._set_factory_mode_locked(True)
        for action in window._factory_lock_actions:
            assert action.isEnabled() is False

    def test_locking_disables_device_deletion(self, main_window):
        window = main_window
        window._set_factory_mode_locked(True)
        assert window.device_panel.remove_button.isEnabled() is False

    def test_locking_disables_firmware_panel_controls(self, main_window):
        window = main_window
        window._set_factory_mode_locked(True)
        assert window.firmware_panel._factory_locked is True

    def test_locking_disables_device_settings_panel(self, main_window):
        window = main_window
        window._set_factory_mode_locked(True)
        # The widget records the locked state and disables its own
        # controls internally; assert the state was actually applied.
        assert window.settings_widget._factory_locked is True

    def test_locking_disables_security_panel(self, main_window):
        window = main_window
        window._set_factory_mode_locked(True)
        assert window.security_widget._factory_locked is True

    def test_unlocking_reenables_everything(self, main_window):
        window = main_window
        window._set_factory_mode_locked(True)
        window._set_factory_mode_locked(False)
        for action in window._factory_lock_actions:
            assert action.isEnabled() is True
        assert window.device_panel.remove_button.isEnabled() is True
        assert window.firmware_panel._factory_locked is False

    def test_settings_lock_does_not_disable_upload_actions(self, main_window):
        """Settings Lock explicitly keeps uploads usable -- only the
        controls that change WHAT/WHERE gets flashed are disabled."""
        window = main_window
        window._set_factory_mode_locked(True)
        # Upload actions are never added to _factory_lock_actions.
        upload_actions = [a for a in window._all_actions if a.text() in ("Upload Selected", "Upload All")]
        assert upload_actions  # sanity: the actions exist
        for action in upload_actions:
            assert action.isEnabled() is True

    def test_toggle_without_a_key_set_prompts_to_set_one_and_stays_unlocked(self, main_window, monkeypatch):
        """Checking 'Settings Lock' with no unlock key configured yet must
        not silently lock the interface -- it should prompt to set a key
        first and leave the checkbox/lock state unchanged."""
        window = main_window
        assert not window.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH)
        monkeypatch.setattr(window, "_on_set_lock_key", lambda: False)
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: None)

        window._on_toggle_factory_lock(True)

        assert window._factory_mode_locked is False
        assert window.factory_lock_action.isChecked() is False

    def test_unlock_with_correct_key_succeeds(self, main_window, monkeypatch):
        window = main_window
        _set_lock_key(window, "correct-key")
        window._set_factory_mode_locked(True)
        monkeypatch.setattr(
            "app.ui.main_window.QInputDialog.getText", lambda *a, **k: ("correct-key", True),
        )
        window._on_toggle_factory_lock(False)
        assert window._factory_mode_locked is False

    def test_unlock_with_wrong_key_stays_locked(self, main_window, monkeypatch):
        window = main_window
        _set_lock_key(window, "correct-key")
        window._set_factory_mode_locked(True)
        window.factory_lock_action.setChecked(True)
        monkeypatch.setattr(
            "app.ui.main_window.QInputDialog.getText", lambda *a, **k: ("wrong-key", True),
        )
        monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
        window._on_toggle_factory_lock(False)
        assert window._factory_mode_locked is True
        assert window.factory_lock_action.isChecked() is True


class TestLegacyKeyHashUpgrade:
    """
    The Interface Lock key hash used to be a single unsalted SHA-256
    round -- verify_lock_key still accepts that old format, and a
    successful verification against it silently upgrades the stored
    hash to the new salted/stretched format so a key set on an older
    release keeps working without ever forcing a reset.
    """

    def test_legacy_hash_still_unlocks(self, main_window, monkeypatch):
        import hashlib

        from app.utilities.constants import SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH

        window = main_window
        legacy_hash = hashlib.sha256(b"old-style-key").hexdigest()
        window.settings.setValue(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH, legacy_hash)
        window._set_factory_mode_locked(True)
        monkeypatch.setattr(
            "app.ui.main_window.QInputDialog.getText", lambda *a, **k: ("old-style-key", True),
        )
        window._on_toggle_factory_lock(False)
        assert window._factory_mode_locked is False

    def test_successful_legacy_verify_upgrades_stored_hash(self, main_window):
        import hashlib

        from app.utilities.constants import SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH
        from app.utilities.key_hashing import is_legacy_hash_format

        window = main_window
        legacy_hash = hashlib.sha256(b"old-style-key").hexdigest()
        window.settings.setValue(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH, legacy_hash)

        assert window._verify_lock_key("old-style-key") is True

        upgraded = window.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH)
        assert upgraded != legacy_hash
        assert is_legacy_hash_format(upgraded) is False
        # And the upgraded hash still verifies the same key correctly.
        assert window._verify_lock_key("old-style-key") is True

    def test_failed_legacy_verify_does_not_upgrade_stored_hash(self, main_window):
        import hashlib

        from app.utilities.constants import SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH

        window = main_window
        legacy_hash = hashlib.sha256(b"old-style-key").hexdigest()
        window.settings.setValue(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH, legacy_hash)

        assert window._verify_lock_key("wrong-key") is False
        assert window.settings.value(SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH) == legacy_hash


class TestFullLockBlocksEverything:
    def test_full_lock_disables_menu_bar_and_central_widget(self, main_window, monkeypatch):
        window = main_window
        _set_lock_key(window, "secret123")
        window._on_lock_interface()
        assert window.menuBar().isEnabled() is False
        assert window.centralWidget().isEnabled() is False

    def test_full_lock_disables_every_tracked_action(self, main_window):
        window = main_window
        _set_lock_key(window, "secret123")
        window._on_lock_interface()
        for action in window._all_actions:
            assert action.isEnabled() is False

    def test_full_lock_shows_overlay(self, main_window):
        window = main_window
        _set_lock_key(window, "secret123")
        window._on_lock_interface()
        assert window.lock_overlay.isVisible() is True

    def test_full_lock_without_key_set_prompts_instead_of_locking(self, main_window, monkeypatch):
        window = main_window
        monkeypatch.setattr(window, "_on_set_lock_key", lambda: False)
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: None)
        window._on_lock_interface()
        assert window.menuBar().isEnabled() is True

    def test_unlock_attempt_with_correct_key_reenables_interface(self, main_window):
        window = main_window
        _set_lock_key(window, "unlock-me")
        window._on_lock_interface()
        window._on_unlock_attempt("unlock-me")
        assert window.menuBar().isEnabled() is True
        assert window.centralWidget().isEnabled() is True
        for action in window._all_actions:
            assert action.isEnabled() is True

    def test_unlock_attempt_with_wrong_key_stays_locked_and_shows_error(self, main_window):
        window = main_window
        _set_lock_key(window, "unlock-me")
        window._on_lock_interface()
        window._on_unlock_attempt("totally-wrong")
        assert window.menuBar().isEnabled() is False
        assert window.lock_overlay.isVisible() is True

    def test_unlock_attempt_with_empty_key_stays_locked(self, main_window):
        window = main_window
        _set_lock_key(window, "unlock-me")
        window._on_lock_interface()
        window._on_unlock_attempt("")
        assert window.menuBar().isEnabled() is False

    def test_full_lock_refuses_when_a_live_console_is_open(self, main_window, monkeypatch):
        """Live Output / Serial Monitor windows are independent, undocked
        windows Interface Lock cannot reach -- Full Lock must refuse to
        engage while one is visible rather than leave a hole in the lock."""
        window = main_window
        _set_lock_key(window, "secret123")

        class FakeConsole:
            def isVisible(self):
                return True

            def windowTitle(self):
                return "Live Output - Bench 1"

            def close(self):
                pass

        window._live_consoles["dev-1"] = FakeConsole()
        monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *a, **k: None)

        window._on_lock_interface()

        assert window.menuBar().isEnabled() is True
        assert window.lock_overlay.isVisible() is False
