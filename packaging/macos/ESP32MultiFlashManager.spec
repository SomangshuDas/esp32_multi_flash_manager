# ESP32MultiFlashManager.spec
# ============================
# macOS-only PyInstaller spec. Building via this spec (instead of the plain
# CLI flags in docs/BUILD_INSTRUCTIONS.md) is what makes double-clicking a
# .efmproj file in Finder, or dragging one onto the Dock icon, launch the
# app with that project pre-loaded: Info.plist's CFBundleDocumentTypes below
# is what tells LaunchServices "this app opens .efmproj files", and Qt/main.py
# picks the resulting QFileOpenEvent up on the ESPFlashApplication subclass.
#
# Run from the repo root:
#   pyinstaller --noconfirm packaging/macos/ESP32MultiFlashManager.spec
#
# (packaging/macos/build_dmg.sh does this for you, plus the .icns generation
# and DMG packaging step.)

# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent.parent

# build_dmg.sh exports APP_VERSION before invoking PyInstaller so the
# .app's version metadata always matches the release tag / -Version arg
# instead of silently staying at a hardcoded default.
app_version = os.environ.get("APP_VERSION", "1.0.0")

a = Analysis(
    [str(repo_root / "run.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[(str(repo_root / "resources"), "resources")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Equivalent of --collect-all esptool on the CLI: pull in esptool's data
# files (stub loaders etc.) that static analysis alone would miss.
from PyInstaller.utils.hooks import collect_all

esptool_datas, esptool_binaries, esptool_hiddenimports = collect_all("esptool")
a.datas += esptool_datas
a.binaries += esptool_binaries
a.hiddenimports += esptool_hiddenimports

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ESP32MultiFlashManager",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="ESP32MultiFlashManager",
)

app = BUNDLE(
    coll,
    name="ESP32MultiFlashManager.app",
    icon=str(repo_root / "resources" / "icons" / "app_icon.icns"),
    bundle_identifier="com.somangshudas.esp32multiflashmanager",
    info_plist={
        "CFBundleName": "ESP32 Multi Flash Manager",
        "CFBundleDisplayName": "ESP32 Multi Flash Manager",
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "NSHumanReadableCopyright": "Copyright (C) Somangshu Das. MIT License.",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "LSMinimumSystemVersion": "10.15",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "ESP32 Multi Flash Manager Project",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.somangshudas.esp32multiflashmanager.efmproj"],
                "CFBundleTypeIconFile": "app_icon.icns",
            }
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": "com.somangshudas.esp32multiflashmanager.efmproj",
                "UTTypeDescription": "ESP32 Multi Flash Manager Project",
                "UTTypeConformsTo": ["public.json", "public.data"],
                "UTTypeTagSpecification": {"public.filename-extension": ["efmproj"]},
            }
        ],
    },
)
