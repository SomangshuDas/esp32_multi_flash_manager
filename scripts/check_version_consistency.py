#!/usr/bin/env python3
"""
scripts/check_version_consistency.py
=====================================
CI/CD and Release Engineering: fails (non-zero exit) if APP_VERSION in
app/utilities/constants.py doesn't match the version declared everywhere
else it's supposed to be kept in sync for a release.

Rather than regex-scanning every "X.Y.Z"-shaped substring across
README.md and docs/**/*.md -- which produces false positives on things
like esptool/PySide6 dependency versions, esptool CLI feature history
("added in tool version 3.9.8"), and historical migration notes
("a key hash set by a pre-0.12.0 build") that are *not* the app's
current version and must NOT be bumped -- this checks an explicit,
unambiguous marker: a `<!-- APP_VERSION: X.Y.Z -->` HTML comment. Every
markdown file that should track the current release version carries
one; docs that only mention version numbers in another context don't.

Currently marked: README.md, CHANGELOG.md. Add the marker to any other
doc that should track APP_VERSION going forward -- this script picks up
every markdown file under the repo root and docs/ that contains one,
so no separate registration step is needed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_RE = re.compile(r"<!--\s*APP_VERSION:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*-->")
APP_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', re.MULTILINE)


def get_app_version() -> str:
    constants_path = REPO_ROOT / "app" / "utilities" / "constants.py"
    text = constants_path.read_text(encoding="utf-8")
    match = APP_VERSION_RE.search(text)
    if not match:
        print(f"::error::Could not find APP_VERSION in {constants_path}")
        sys.exit(1)
    return match.group(1)


def find_marked_files() -> list[Path]:
    candidates = [REPO_ROOT / "README.md", REPO_ROOT / "CHANGELOG.md"]
    candidates += sorted((REPO_ROOT / "docs").rglob("*.md"))
    seen = set()
    result = []
    for path in candidates:
        if path.is_file() and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def main() -> int:
    app_version = get_app_version()
    print(f"APP_VERSION = {app_version}")

    mismatches = []
    checked_any = False
    for path in find_marked_files():
        text = path.read_text(encoding="utf-8")
        match = MARKER_RE.search(text)
        if not match:
            continue
        checked_any = True
        marked_version = match.group(1)
        relative = path.relative_to(REPO_ROOT)
        if marked_version != app_version:
            mismatches.append((relative, marked_version))
        else:
            print(f"OK: {relative} declares {marked_version}")

    if not checked_any:
        print(
            "::error::No <!-- APP_VERSION: X.Y.Z --> marker found in README.md, "
            "CHANGELOG.md, or docs/**/*.md -- add one so this check has something "
            "to verify."
        )
        return 1

    if mismatches:
        for relative, marked_version in mismatches:
            print(
                f"::error file={relative}::{relative} declares APP_VERSION "
                f"{marked_version}, but app/utilities/constants.py has {app_version}. "
                "Update the marker (and the rest of that file's version mentions) "
                "to match."
            )
        return 1

    print("All version markers match APP_VERSION.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
