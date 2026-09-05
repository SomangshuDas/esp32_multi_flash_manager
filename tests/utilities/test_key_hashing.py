"""Unit tests for app/utilities/key_hashing.py."""

from __future__ import annotations

import hashlib

from app.utilities import key_hashing

# Low iteration count everywhere in these tests so PBKDF2 stays fast --
# production uses key_hashing's own much higher default.
_FAST_ITERATIONS = 100


class TestHashAndVerify:
    def test_correct_key_verifies(self):
        stored = key_hashing.hash_lock_key("hunter2", iterations=_FAST_ITERATIONS)
        assert key_hashing.verify_lock_key("hunter2", stored) is True

    def test_wrong_key_does_not_verify(self):
        stored = key_hashing.hash_lock_key("hunter2", iterations=_FAST_ITERATIONS)
        assert key_hashing.verify_lock_key("wrong", stored) is False

    def test_stored_format_is_self_describing(self):
        stored = key_hashing.hash_lock_key("k", iterations=_FAST_ITERATIONS)
        algo, iterations, salt_hex, digest_hex = stored.split("$", 3)
        assert algo == "pbkdf2_sha256"
        assert int(iterations) == _FAST_ITERATIONS
        assert len(bytes.fromhex(salt_hex)) == 16
        assert len(bytes.fromhex(digest_hex)) == 32  # SHA-256 digest size

    def test_same_key_produces_different_hashes_due_to_random_salt(self):
        a = key_hashing.hash_lock_key("same-key", iterations=_FAST_ITERATIONS)
        b = key_hashing.hash_lock_key("same-key", iterations=_FAST_ITERATIONS)
        assert a != b
        assert key_hashing.verify_lock_key("same-key", a) is True
        assert key_hashing.verify_lock_key("same-key", b) is True

    def test_empty_stored_never_verifies(self):
        assert key_hashing.verify_lock_key("anything", "") is False
        assert key_hashing.verify_lock_key("anything", None) is False

    def test_corrupt_stored_value_does_not_raise(self):
        assert key_hashing.verify_lock_key("k", "pbkdf2_sha256$not-an-int$zz$zz") is False
        assert key_hashing.verify_lock_key("k", "not-even-the-right-shape") is False


class TestLegacyFormatCompatibility:
    def test_legacy_unsalted_sha256_is_detected(self):
        legacy = hashlib.sha256(b"oldkey").hexdigest()
        assert key_hashing.is_legacy_hash_format(legacy) is True

    def test_new_format_is_not_legacy(self):
        stored = key_hashing.hash_lock_key("k", iterations=_FAST_ITERATIONS)
        assert key_hashing.is_legacy_hash_format(stored) is False

    def test_legacy_hash_still_verifies_correct_key(self):
        legacy = hashlib.sha256(b"oldkey").hexdigest()
        assert key_hashing.verify_lock_key("oldkey", legacy) is True

    def test_legacy_hash_rejects_wrong_key(self):
        legacy = hashlib.sha256(b"oldkey").hexdigest()
        assert key_hashing.verify_lock_key("wrongkey", legacy) is False
