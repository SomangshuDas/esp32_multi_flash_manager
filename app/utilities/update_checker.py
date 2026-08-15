"""
update_checker.py
==================
Checks GitHub Releases for a newer version of this application. This app
never downloads or applies updates in place — if a newer version exists,
the caller opens the browser straight to that release's download (with
the file matching the current OS *and* the current build kind
pre-selected whenever possible) and exits, leaving the actual install to
the user's normal OS installer flow.

"Build kind" means portable vs. installer. release.yml uploads BOTH a raw
portable PyInstaller build and a proper OS installer for every platform.
Handing an installed user the portable exe (no Start Menu entry, no file
association, no clean uninstall) or handing a portable user the installer
(admin prompt, registry writes) is the wrong asset either way, so
`check_for_update()` picks the pattern order using `is_portable_build()`:
installed users get installer-first matching, portable users get
portable-first matching. Either list still falls through to the other
kind as a last resort, so a release that only shipped one kind of asset
still resolves to *something* instead of nothing.

Network access always fails soft: any error (offline, rate-limited,
malformed response) returns None rather than raising, so "Check for
Updates" can never crash the app.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.logging_setup.logger import get_logger
from app.utilities.constants import APP_VERSION, GITHUB_REPO, INSTALL_MARKER_FILENAME

logger = get_logger(__name__)

_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
_REQUEST_TIMEOUT_SECONDS = 6

# Asset-name patterns per platform, split by build kind. Order within each
# tuple matters (first match wins); the two tuples are concatenated in the
# preferred order for the running build kind by _pick_asset() below.
_INSTALLER_ASSET_PATTERNS = {
    "win32": (r"setup.*\.exe$",),
    "darwin": (r"\.dmg$", r"\.pkg$"),
    "linux": (r"\.appimage$", r"\.deb$"),
}
_PORTABLE_ASSET_PATTERNS = {
    "win32": (r"windows.*\.exe$", r"win64", r"win", r"\.exe$"),
    "darwin": (r"macos", r"mac"),
    "linux": (r"linux(?!.*appimage)", r"\.tar\.gz$"),
}


def is_portable_build() -> bool:
    """
    True if this running build should be treated as "portable" (a bare
    single-file executable / AppImage / .app with no OS install step),
    False if it should be treated as "installed" (put there by an OS
    installer such as Windows' Setup.exe).

    - Running from source (not frozen by PyInstaller) is always
      "portable" -- there is no install step to speak of.
    - A frozen build is "installed" only if INSTALL_MARKER_FILENAME sits
      next to the executable. Windows' installer.iss drops that marker at
      install time; nothing does on macOS/Linux today (the .dmg/.AppImage
      builds are drag-and-run, not a true install step), so those always
      resolve to "portable" unless a future installer starts dropping the
      same marker file.
    """
    if not getattr(sys, "frozen", False):
        return True
    exe_dir = Path(sys.executable).resolve().parent
    return not (exe_dir / INSTALL_MARKER_FILENAME).is_file()


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
    """True if `remote_version` (e.g. 'v0.5.0' or '0.5.0') is strictly
    newer than `local_version`, comparing numeric release components."""
    return _parse_version(remote_version) > _parse_version(local_version)


def _pick_asset(assets: list[dict], prefer_portable: bool) -> tuple[str | None, str | None]:
    """
    Return (download_url, filename) for the asset that best matches both
    the OS this build is running on and its build kind (portable vs.
    installer), or (None, None) if nothing matched.

    `prefer_portable` controls which kind's patterns are tried first; the
    other kind's patterns are still appended afterwards as a fallback, so
    a release that only shipped one kind of asset still resolves.
    """
    installer_patterns = _INSTALLER_ASSET_PATTERNS.get(sys.platform, ())
    portable_patterns = _PORTABLE_ASSET_PATTERNS.get(sys.platform, ())
    patterns = (portable_patterns + installer_patterns) if prefer_portable else (installer_patterns + portable_patterns)
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

    raw_tag = str(payload.get("tag_name", "")).strip()
    if not raw_tag or not is_newer(raw_tag):
        return None

    # GitHub tag names are "v"-prefixed (e.g. "v0.5.0"). Callers that display
    # this value prepend their own "v" (e.g. f"v{info.version}"), so strip
    # the prefix here rather than storing it raw -- otherwise the UI ends up
    # showing a doubled "vv0.5.0".
    remote_version = raw_tag.lstrip("vV")

    page_url = payload.get("html_url", _RELEASES_PAGE_URL)
    portable = is_portable_build()
    asset_url, asset_name = _pick_asset(payload.get("assets", []) or [], prefer_portable=portable)

    logger.info(
        "Update available: %s -> %s (build kind: %s)",
        APP_VERSION, remote_version, "portable" if portable else "installed",
    )
    return UpdateInfo(version=remote_version, page_url=page_url, asset_url=asset_url, asset_name=asset_name)
