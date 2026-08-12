"""
update_checker.py
==================
Checks GitHub Releases for a newer version of this application. This app
never downloads or applies updates in place — if a newer version exists,
the caller opens the browser straight to that release's download (with
the file matching the current OS pre-selected whenever possible) and
exits, leaving the actual install to the user's normal OS installer flow.

Network access always fails soft: any error (offline, rate-limited,
malformed response) returns None rather than raising, so "Check for
Updates" can never crash the app.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.logging_setup.logger import get_logger
from app.utilities.constants import APP_VERSION, GITHUB_REPO

logger = get_logger(__name__)

_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
_REQUEST_TIMEOUT_SECONDS = 6

# Asset-name patterns to try, in order, for each platform. The first
# release asset whose filename matches one of these wins.
_ASSET_PATTERNS = {
    "win32": (r"windows", r"win64", r"win", r"setup.*\.exe$", r"\.exe$"),
    "darwin": (r"macos", r"mac", r"\.dmg$", r"\.pkg$"),
    "linux": (r"linux", r"\.appimage$", r"\.deb$", r"\.tar\.gz$"),
}


@dataclass
class UpdateInfo:
    version: str
    page_url: str
    asset_url: str | None
    asset_name: str | None

    @property
    def target_url(self) -> str:
        """Best URL to send the user to: the matching asset if one was
        found, otherwise the release page itself."""
        return self.asset_url or self.page_url


def _parse_version(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    return tuple(int(p) for p in parts) or (0,)


def is_newer(remote_version: str, local_version: str = APP_VERSION) -> bool:
    """True if `remote_version` (e.g. 'v0.4.0' or '0.4.0') is strictly
    newer than `local_version`, comparing numeric release components."""
    return _parse_version(remote_version) > _parse_version(local_version)


def _pick_asset(assets: list[dict]) -> tuple[str | None, str | None]:
    """Return (download_url, filename) for the asset that best matches the
    OS this build is running on, or (None, None) if nothing matched."""
    patterns = _ASSET_PATTERNS.get(sys.platform, ())
    for pattern in patterns:
        for asset in assets:
            name = asset.get("name", "")
            if re.search(pattern, name, re.IGNORECASE):
                return asset.get("browser_download_url"), name
    return None, None


def check_for_update() -> UpdateInfo | None:
    """
    Query GitHub's "latest release" endpoint. Returns None if the request
    fails, the response is malformed, or the app is already up to date.
    Otherwise returns an UpdateInfo describing the newer version and the
    release asset most likely matching the platform running this build.
    """
    request = Request(
        _RELEASES_API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ESP32MultiFlashManager"},
    )
    try:
        with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Update check failed: %s", exc)
        return None

    remote_version = str(payload.get("tag_name", "")).strip()
    if not remote_version or not is_newer(remote_version):
        return None

    page_url = payload.get("html_url", _RELEASES_PAGE_URL)
    asset_url, asset_name = _pick_asset(payload.get("assets", []) or [])

    logger.info("Update available: %s -> %s", APP_VERSION, remote_version)
    return UpdateInfo(version=remote_version, page_url=page_url, asset_url=asset_url, asset_name=asset_name)
