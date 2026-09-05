"""Unit tests for app/utilities/update_checker.py's version comparison."""

from __future__ import annotations

import pytest

from app.utilities import update_checker


class TestIsNewer:
    def test_higher_patch_is_newer(self):
        assert update_checker.is_newer("0.11.1", "0.11.0") is True

    def test_lower_patch_is_not_newer(self):
        assert update_checker.is_newer("0.11.0", "0.11.1") is False

    def test_equal_versions_not_newer(self):
        assert update_checker.is_newer("0.11.0", "0.11.0") is False

    def test_v_prefix_is_ignored(self):
        assert update_checker.is_newer("v0.12.0", "0.11.0") is True

    def test_prerelease_is_not_newer_than_its_own_plain_release(self):
        # This is the exact bug being fixed: naive digit extraction parsed
        # "1.2.3-rc1" as (1, 2, 3, 1), which sorted as *newer* than the
        # plain "1.2.3" release. A pre-release must never outrank its own
        # release.
        assert update_checker.is_newer("1.2.3-rc1", "1.2.3") is False

    def test_plain_release_is_newer_than_its_own_prerelease(self):
        assert update_checker.is_newer("1.2.3", "1.2.3-rc1") is True

    def test_higher_prerelease_number_is_newer_among_prereleases(self):
        assert update_checker.is_newer("1.2.3-rc2", "1.2.3-rc1") is True
        assert update_checker.is_newer("1.2.3-rc1", "1.2.3-rc2") is False

    def test_prerelease_of_higher_release_is_still_newer(self):
        # A pre-release of a genuinely newer version is still newer than
        # the current plain release.
        assert update_checker.is_newer("1.3.0-rc1", "1.2.3") is True

    @pytest.mark.parametrize(
        "remote,local,expected",
        [
            ("2.0.0", "1.9.9", True),
            ("1.9.9", "2.0.0", False),
            ("1.0.0-beta.2", "1.0.0-beta.1", True),
            ("1.0.0-beta.1", "1.0.0-beta.2", False),
        ],
    )
    def test_parametrized_cases(self, remote, local, expected):
        assert update_checker.is_newer(remote, local) is expected
