"""
key_hashing.py
===============
Hashing for the Interface Lock unlock key (Tools -> Set Interface Lock
Key..., see app/ui/main_window.py). The stored hash lives in settings.json
under SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH.

This app previously hashed the key with a single, unsalted SHA-256 round
(``hashlib.sha256(key.encode()).hexdigest()``). Since settings.json sits
in plain text in the user's app-data folder, anyone who can read that one
file could brute-force a short PIN/passphrase offline at SHA-256 speed
(billions of guesses/second on commodity hardware) with no per-install
salt to defeat precomputed tables. This module replaces that with a
per-key random salt plus PBKDF2-HMAC-SHA256 key stretching, using the
stdlib's own ``hashlib.pbkdf2_hmac`` (no extra dependency needed).

Stored format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`` --
self-describing so the algorithm/iteration count can be upgraded later
without invalidating keys set by an older release (see verify_lock_key's
legacy-format fallback below).
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ALGO_TAG = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 260_000  # OWASP's 2023 minimum recommendation for PBKDF2-HMAC-SHA256
_SALT_BYTES = 16


def hash_lock_key(key: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """Return a salted, stretched hash of `key` in the self-describing
    stored format described in this module's docstring."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations)
    return f"{_ALGO_TAG}${iterations}${salt.hex()}${digest.hex()}"


def _verify_legacy_unsalted_sha256(key: str, stored: str) -> bool:
    """Verify against the OLD unsalted single-round SHA-256 format (a bare
    64-char hex digest, no '$'-separated fields) so a key set by a
    pre-upgrade release still unlocks correctly instead of permanently
    locking the user out. See is_legacy_hash_format()."""
    legacy_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_digest, stored)


def is_legacy_hash_format(stored: str) -> bool:
    """True if `stored` looks like the old unsalted single-round SHA-256
    format rather than this module's salted/stretched format -- callers
    (see MainWindow) use this to silently re-hash and upgrade a legacy
    key the next time it's successfully verified."""
    return bool(stored) and "$" not in stored


def verify_lock_key(key: str, stored: str) -> bool:
    """
    Return True if `key` matches `stored` (as produced by hash_lock_key,
    or a legacy unsalted-SHA-256 hash from before this fix). Never raises
    on a malformed/corrupt stored value -- treats it as a non-match.
    """
    if not stored:
        return False
    if is_legacy_hash_format(stored):
        return _verify_legacy_unsalted_sha256(key, stored)
    try:
        algo, iterations_str, salt_hex, digest_hex = stored.split("$", 3)
        if algo != _ALGO_TAG:
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
