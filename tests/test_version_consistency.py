"""
tests/test_version_consistency.py
===================================
Exercises scripts/check_version_consistency.py directly (importing it as
a module, not shelling out) so this is also caught by the regular test
suite -- not just the dedicated version_check.yml CI workflow -- if a
release ever ships with APP_VERSION out of sync with README.md/
CHANGELOG.md's `<!-- APP_VERSION: X.Y.Z -->` markers.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_version_consistency.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_version_consistency", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_currently_passes_the_version_check():
    module = _load_script_module()
    assert module.main() == 0


def test_app_version_and_readme_marker_actually_match():
    module = _load_script_module()
    app_version = module.get_app_version()
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    match = module.MARKER_RE.search(readme_text)
    assert match is not None, "README.md is missing its <!-- APP_VERSION: X.Y.Z --> marker"
    assert match.group(1) == app_version


def test_app_version_and_changelog_marker_actually_match():
    module = _load_script_module()
    app_version = module.get_app_version()
    changelog_text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = module.MARKER_RE.search(changelog_text)
    assert match is not None, "CHANGELOG.md is missing its <!-- APP_VERSION: X.Y.Z --> marker"
    assert match.group(1) == app_version


def test_mismatched_marker_is_detected(monkeypatch, tmp_path):
    module = _load_script_module()

    fake_root = tmp_path
    (fake_root / "app" / "utilities").mkdir(parents=True)
    (fake_root / "app" / "utilities" / "constants.py").write_text('APP_VERSION = "1.2.3"\n')
    (fake_root / "README.md").write_text("<!-- APP_VERSION: 9.9.9 -->\n# Title\n")
    (fake_root / "docs").mkdir()

    monkeypatch.setattr(module, "REPO_ROOT", fake_root)
    assert module.main() == 1


def test_no_marker_anywhere_is_treated_as_an_error(monkeypatch, tmp_path):
    module = _load_script_module()

    fake_root = tmp_path
    (fake_root / "app" / "utilities").mkdir(parents=True)
    (fake_root / "app" / "utilities" / "constants.py").write_text('APP_VERSION = "1.2.3"\n')
    (fake_root / "README.md").write_text("# Title, no marker here\n")
    (fake_root / "docs").mkdir()

    monkeypatch.setattr(module, "REPO_ROOT", fake_root)
    assert module.main() == 1
