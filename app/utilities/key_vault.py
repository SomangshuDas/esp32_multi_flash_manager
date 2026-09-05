"""
key_vault.py
============
Optional OS-keychain-backed storage for generated flash-encryption /
secure-boot key material (app/flash_engine/security_manager.py), as an
alternative to the key file sitting purely as plaintext bytes on local
disk.

Backed by the ``keyring`` package, which talks to whatever secure-storage
backend the running OS actually provides: Windows Credential Locker,
macOS/iOS Keychain, or the Secret Service API (GNOME Keyring/KWallet) on
Linux. None of those are a hardware security module (HSM) -- genuine HSM
or PKCS#11 support needs dedicated hardware/middleware this app has no way
to depend on generically, so this module intentionally does not claim
that. What it does provide is "don't leave the only copy of a generated
key sitting as a plain file with the same permissions as everything
else" for platforms with a working OS keychain.

Fails soft everywhere: any backend/platform without a working keychain
(headless Linux with no Secret Service daemon, a locked-down machine,
`keyring` not installed, etc.) makes every function here a no-op that
returns False/None rather than raising, so a build without a usable
keychain still works exactly as before (key file on disk only).
"""

from __future__ import annotations

from pathlib import Path

from app.logging_setup.logger import get_logger

logger = get_logger(__name__)

# All entries live under one keyring "service" name, keyed by an
# identifier the caller supplies (see key_identifier_for_path below) so
# multiple devices'/projects' keys don't collide with each other.
_SERVICE_NAME = "ESP32MultiFlashManager-KeyVault"


def is_available() -> bool:
    """True if a real, working OS keychain backend is reachable right now
    (not just that the `keyring` package is importable -- a headless
    Linux box with no Secret Service daemon running has the package but
    no usable backend)."""
    try:
        import keyring

        backend = keyring.get_keyring()
        # Round-trip a throwaway value; the fail/null backends keyring
        # falls back to raise NoKeyringError (or silently no-op, which
        # would falsely report "available") -- setting AND reading back
        # a real value with a real backend is the only reliable check.
        probe_key = "__key_vault_availability_probe__"
        backend.set_password(_SERVICE_NAME, probe_key, "1")
        ok = backend.get_password(_SERVICE_NAME, probe_key) == "1"
        backend.delete_password(_SERVICE_NAME, probe_key)
        return ok
    except Exception:  # noqa: BLE001 - any backend failure means "unavailable"
        return False


def key_identifier_for_path(key_path: str) -> str:
    """Stable keyring entry name derived from a key file's own path, so
    the same file always maps to the same vault entry."""
    return Path(key_path).resolve().as_posix()


def store_key_file(key_path: str) -> bool:
    """
    Read the key file at `key_path` and copy its bytes into the OS
    keychain under an entry derived from its path. Does NOT delete the
    original file (the caller decides whether to keep, since the file
    still needs to exist for espsecure/espefuse to read at burn time
    unless retrieve_key_file() below is used to restore it first).

    Returns True on success, False on any failure (missing file, no
    backend available, key too large for the backend, etc.) -- never
    raises, since this is always an optional hardening step layered on
    top of the file already existing on disk.
    """
    try:
        import keyring
    except ImportError:
        logger.info("key_vault: 'keyring' package not installed; skipping OS-keychain storage.")
        return False

    path = Path(key_path)
    if not path.is_file():
        logger.warning("key_vault: cannot vault missing key file %s", key_path)
        return False

    try:
        data = path.read_bytes()
        import base64
        encoded = base64.b64encode(data).decode("ascii")
        keyring.set_password(_SERVICE_NAME, key_identifier_for_path(key_path), encoded)
        logger.info("key_vault: stored a copy of %s in the OS keychain.", key_path)
        return True
    except Exception:  # noqa: BLE001 - vaulting is always best-effort
        logger.exception("key_vault: failed to store %s in the OS keychain", key_path)
        return False


def retrieve_key_file(key_path: str) -> bytes | None:
    """Return the bytes previously stored for `key_path` via
    store_key_file(), or None if nothing is stored / no backend is
    available / retrieval fails."""
    try:
        import keyring
    except ImportError:
        return None
    try:
        encoded = keyring.get_password(_SERVICE_NAME, key_identifier_for_path(key_path))
        if encoded is None:
            return None
        import base64
        return base64.b64decode(encoded)
    except Exception:  # noqa: BLE001
        logger.exception("key_vault: failed to retrieve vaulted copy of %s", key_path)
        return None


def delete_key_file(key_path: str) -> bool:
    """Remove any vaulted copy of `key_path`. Returns True if something
    was actually deleted, False otherwise (including "nothing was
    stored" and "no backend available") -- never raises."""
    try:
        import keyring
    except ImportError:
        return False
    try:
        keyring.delete_password(_SERVICE_NAME, key_identifier_for_path(key_path))
        return True
    except Exception:  # noqa: BLE001 - covers keyring.errors.PasswordDeleteError etc.
        return False
