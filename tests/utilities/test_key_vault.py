"""
Unit tests for app/utilities/key_vault.py.

A fake in-memory keyring backend is installed via monkeypatch so these
tests never touch a real OS keychain (and pass identically on any CI
runner, with or without a working Secret Service/Credential Locker).
"""

from __future__ import annotations

import pytest

from app.utilities import key_vault


class _FakeKeyring:
    """Minimal stand-in for the `keyring` module's public functions."""

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service, key, value):
        self._store[(service, key)] = value

    def get_password(self, service, key):
        return self._store.get((service, key))

    def delete_password(self, service, key):
        if (service, key) not in self._store:
            raise KeyError("not found")
        del self._store[(service, key)]

    def get_keyring(self):
        return self


@pytest.fixture
def fake_keyring(monkeypatch):
    fake = _FakeKeyring()
    import sys
    import types

    module = types.ModuleType("keyring")
    module.set_password = fake.set_password
    module.get_password = fake.get_password
    module.delete_password = fake.delete_password
    module.get_keyring = fake.get_keyring
    monkeypatch.setitem(sys.modules, "keyring", module)
    return fake


class TestIsAvailable:
    def test_true_with_working_fake_backend(self, fake_keyring):
        assert key_vault.is_available() is True

    def test_false_when_keyring_not_installed(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "keyring", None)
        assert key_vault.is_available() is False


class TestStoreRetrieveDelete:
    def test_store_and_retrieve_round_trip(self, fake_keyring, tmp_path):
        key_file = tmp_path / "key.bin"
        key_file.write_bytes(b"\x01\x02\x03secret-key-bytes")

        assert key_vault.store_key_file(str(key_file)) is True
        retrieved = key_vault.retrieve_key_file(str(key_file))
        assert retrieved == b"\x01\x02\x03secret-key-bytes"

    def test_store_missing_file_returns_false(self, fake_keyring, tmp_path):
        missing = tmp_path / "does_not_exist.bin"
        assert key_vault.store_key_file(str(missing)) is False

    def test_retrieve_nonexistent_entry_returns_none(self, fake_keyring, tmp_path):
        key_file = tmp_path / "never_stored.bin"
        key_file.write_bytes(b"data")
        assert key_vault.retrieve_key_file(str(key_file)) is None

    def test_delete_removes_stored_entry(self, fake_keyring, tmp_path):
        key_file = tmp_path / "key.bin"
        key_file.write_bytes(b"secret")
        key_vault.store_key_file(str(key_file))
        assert key_vault.delete_key_file(str(key_file)) is True
        assert key_vault.retrieve_key_file(str(key_file)) is None

    def test_delete_nonexistent_returns_false(self, fake_keyring, tmp_path):
        key_file = tmp_path / "never_stored.bin"
        assert key_vault.delete_key_file(str(key_file)) is False


class TestFailsSoftWithoutKeyring:
    def test_store_returns_false_when_keyring_not_installed(self, monkeypatch, tmp_path):
        import sys

        monkeypatch.setitem(sys.modules, "keyring", None)
        key_file = tmp_path / "key.bin"
        key_file.write_bytes(b"secret")
        assert key_vault.store_key_file(str(key_file)) is False

    def test_retrieve_returns_none_when_keyring_not_installed(self, monkeypatch, tmp_path):
        import sys

        monkeypatch.setitem(sys.modules, "keyring", None)
        assert key_vault.retrieve_key_file(str(tmp_path / "key.bin")) is None
