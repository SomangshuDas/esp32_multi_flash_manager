"""
constants.py
============
Central location for every "magic value" used across the application.
Keeping these in one module avoids scattering literals across the codebase
and makes future firmware/chip support trivial to extend.
"""

from __future__ import annotations

APP_NAME = "ESP32 Multi Flash Manager"
APP_VERSION = "0.8.0"
ORG_NAME = "Somangshu Das"

# --------------------------------------------------------------------------
# Chip / flashing parameter choices (mirrors what esptool.py itself accepts)
# --------------------------------------------------------------------------
# This list is now only a LAST-RESORT FALLBACK. At startup the app queries
# the installed `esptool` package itself for the chips it actually supports
# (see app/utilities/chip_detect.py) so newly-released chip targets show up
# automatically without a code change here. This constant is only used if
# that dynamic detection fails for some reason (esptool missing/broken).
SUPPORTED_CHIPS = [
    "auto",
    "esp32",
    "esp32s2",
    "esp32s3",
    "esp32c3",
    "esp32c6",
    "esp32h2",
    "esp8266",
]

BAUD_RATES = [
    9600, 19200, 38400, 57600, 74880, 115200, 230400,
    460800, 512000, 921600, 1500000, 2000000,
]

FLASH_MODES = ["keep", "qio", "qout", "dio", "dout"]
FLASH_FREQUENCIES = ["keep", "40m", "26m", "20m", "80m"]
FLASH_SIZES = [
    "keep", "1MB", "2MB", "2MB-c1", "4MB", "4MB-c1",
    "8MB", "16MB", "32MB",
]
COMPRESSION_MODES = ["default (compressed)", "uncompressed (-u)"]

DEFAULT_BAUD = 115200
DEFAULT_FLASH_MODE = "keep"
DEFAULT_FLASH_FREQ = "keep"
DEFAULT_FLASH_SIZE = "keep"
DEFAULT_CHIP = "auto"

# --------------------------------------------------------------------------
# Theme (app/ui/theme.py)
# --------------------------------------------------------------------------
# "system" is not itself a stylesheet -- it means "resolve to dark/light by
# asking the OS", re-evaluated live whenever the OS scheme changes (see
# MainWindow._apply_theme / theme.resolve_theme). It is the default so a
# fresh install matches the user's OS preference from the very first launch
# instead of always opening in dark mode.
THEME_SYSTEM = "system"
THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_OPTIONS = [THEME_SYSTEM, THEME_DARK, THEME_LIGHT]
THEME_OPTION_LABELS = {
    THEME_SYSTEM: "System Default",
    THEME_DARK: "Dark",
    THEME_LIGHT: "Light",
}
DEFAULT_THEME = THEME_SYSTEM
SETTINGS_KEY_THEME = "theme"

# --------------------------------------------------------------------------
# Known firmware image name -> default flash address mapping.
# Used by the auto-detection engine when a firmware folder is imported.
# Addresses follow Espressif's standard ESP-IDF partition layout.
# --------------------------------------------------------------------------
KNOWN_FIRMWARE_ADDRESSES: dict[str, str] = {
    "bootloader.bin": "0x1000",
    "partition-table.bin": "0x8000",
    "partitions.bin": "0x8000",
    "ota_data_initial.bin": "0xd000",
    "boot_app0.bin": "0xe000",
    "firmware.bin": "0x10000",
    "app.bin": "0x10000",
}

# --------------------------------------------------------------------------
# Device status enum values (kept as plain strings for JSON-friendliness)
# --------------------------------------------------------------------------
STATUS_WAITING = "Waiting"
STATUS_PREPARING = "Preparing"
STATUS_CONNECTING = "Connecting"
STATUS_ERASING = "Erasing"
STATUS_UPLOADING = "Uploading"
STATUS_VERIFYING = "Verifying"
STATUS_COMPLETED = "Completed"
STATUS_CANCELLED = "Cancelled"
STATUS_FAILED = "Failed"

STATUS_COLORS = {
    STATUS_WAITING: "#8a8f98",
    STATUS_PREPARING: "#5b8def",
    STATUS_CONNECTING: "#5b8def",
    STATUS_ERASING: "#e0a300",
    STATUS_UPLOADING: "#2f9e44",
    STATUS_VERIFYING: "#1c7ed6",
    STATUS_COMPLETED: "#2f9e44",
    STATUS_CANCELLED: "#868e96",
    STATUS_FAILED: "#e03131",
}

ACTIVE_STATUSES = {
    STATUS_PREPARING, STATUS_CONNECTING, STATUS_ERASING,
    STATUS_UPLOADING, STATUS_VERIFYING,
}

# --------------------------------------------------------------------------
# How long FlashWorker waits for a new line of esptool output before
# deciding the subprocess is hung rather than merely slow (e.g. a device
# that disconnects mid-write, leaving the OS serial driver blocked in an
# uninterruptible I/O wait that esptool itself never times out on). Past
# this many seconds of total silence, the worker kills the subprocess and
# fails the device instead of leaving its status stuck on "Uploading"
# forever (which also permanently blocked that port's Serial Monitor).
# --------------------------------------------------------------------------
FLASH_STALL_TIMEOUT_SECONDS = 45.0

# --------------------------------------------------------------------------
# File / project extensions
# --------------------------------------------------------------------------
PROJECT_FILE_EXTENSION = "efmproj"
PROJECT_FILE_FILTER = "ESP32 Multi Flash Manager Project (*.efmproj)"
FIRMWARE_FILE_FILTER = "Firmware Binary (*.bin)"

# --------------------------------------------------------------------------
# Internal flag used to re-invoke this same executable as an esptool runner.
#
# esptool is launched as a subprocess via `sys.executable`. When running
# from source that's a real Python interpreter, so `-m esptool` works. But
# in a PyInstaller --onefile build, `sys.executable` IS this app's own .exe
# -- there is no separate Python on the target machine. main.py intercepts
# this flag at startup: if present, it runs esptool's CLI directly (esptool
# is bundled in via `--collect-all esptool`) and exits immediately instead
# of opening the GUI. Without this, a frozen build's "Upload" would instead
# relaunch a second blank instance of the app and never actually flash.
# --------------------------------------------------------------------------
ESPTOOL_REEXEC_FLAG = "--_run-esptool"

# Same fast-path re-exec trick as ESPTOOL_REEXEC_FLAG above, but for the two
# sibling console tools that ship inside the `esptool` PyPI distribution:
# `espsecure` (key generation / image signing for flash encryption + secure
# boot) and `espefuse` (burning/reading eFuses). Security provisioning is
# built entirely on these two official tools -- this app never implements
# any cryptographic or eFuse-protocol logic itself (see
# app/flash_engine/security_manager.py). See main.py for the interception.
ESPSECURE_REEXEC_FLAG = "--_run-espsecure"
ESPEFUSE_REEXEC_FLAG = "--_run-espefuse"

# --------------------------------------------------------------------------
# Misc UI constants
# --------------------------------------------------------------------------
MAX_RECENT_PROJECTS = 10
PORT_SCAN_INTERVAL_MS = 2000
LIVE_LOG_MAX_LINES = 10000

# --------------------------------------------------------------------------
# Update checking (GitHub Releases)
# --------------------------------------------------------------------------
GITHUB_REPO = "SomangshuDas/esp32_multi_flash_manager"

# Help -> User Manual opens this file straight from GitHub so it's always
# in sync with the branch, rather than bundling (and going stale against)
# a local copy inside the packaged app.
USER_MANUAL_URL = f"https://github.com/{GITHUB_REPO}/blob/main/docs/USER_MANUAL.md"

# Dropped next to the executable by an OS installer (Windows Setup.exe) so
# a frozen build can tell "installed" apart from "portable" at runtime.
# Its presence is what lets update_checker.py offer an installer asset to
# installed users and a portable asset to portable users instead of always
# guessing. See update_checker.py's module docstring for the full picture.
INSTALL_MARKER_FILENAME = "install_marker.txt"

# --------------------------------------------------------------------------
# Bin Merge (app/firmware_manager/bin_merge.py, app/ui/merge_bin_dialog.py)
# --------------------------------------------------------------------------
# Merging turns a device's separate firmware images (bootloader, partition
# table, app, ...) into one flashable image via `esptool merge-bin`.
DEFAULT_MERGED_BIN_FILENAME = "merged-firmware.bin"

# settings.json keys for the app-wide defaults configured in Settings...
SETTINGS_KEY_MERGE_DEFAULT_FILENAME = "merge_default_filename"
SETTINGS_KEY_MERGE_DEFAULT_LOCATION = "merge_default_location"
SETTINGS_KEY_MERGE_POST_ACTION = "merge_post_action"

# ...and what a device's merge output defaults to when Settings hasn't been
# customized: same file name as the fallback above, and the SAME FOLDER AS
# firmware.bin (i.e. blank -- resolved at merge time from the device's own
# firmware list, never a fixed path baked in here).
DEFAULT_MERGE_OUTPUT_LOCATION = ""  # blank == "same folder as firmware.bin"

# What happens to the source BIN rows in Firmware Settings after a
# successful merge. The dialog always lets the user pick one of these for
# that specific merge; MERGE_POST_ACTION_DEFAULT is only what's pre-selected
# when the dialog opens (itself overridable in Settings).
MERGE_POST_ACTION_ADD_DESELECT = "add_deselect"  # add merged bin, de-select (but keep) the source bins
MERGE_POST_ACTION_ADD_REMOVE = "add_remove"      # add merged bin, remove the source bins entirely
MERGE_POST_ACTION_ADD_ONLY = "add_only"          # add merged bin, leave source bins untouched
MERGE_POST_ACTION_NONE = "none"                  # just write the file, don't touch Firmware Settings

MERGE_POST_ACTIONS = [
    MERGE_POST_ACTION_ADD_DESELECT,
    MERGE_POST_ACTION_ADD_REMOVE,
    MERGE_POST_ACTION_ADD_ONLY,
    MERGE_POST_ACTION_NONE,
]
MERGE_POST_ACTION_LABELS: dict[str, str] = {
    MERGE_POST_ACTION_ADD_DESELECT: "Add merged bin, de-select source bins",
    MERGE_POST_ACTION_ADD_REMOVE: "Add merged bin, remove source bins",
    MERGE_POST_ACTION_ADD_ONLY: "Add merged bin only (leave source bins as-is)",
    MERGE_POST_ACTION_NONE: "Do nothing to Firmware Settings",
}
DEFAULT_MERGE_POST_ACTION = MERGE_POST_ACTION_ADD_DESELECT

# --------------------------------------------------------------------------
# Interface Lock (app/ui/main_window.py)
# --------------------------------------------------------------------------
# Two independent lock modes, grouped under the Tools -> Lock Interface
# submenu, both gated behind the same unlock-key hash
# (SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH) set via Tools -> Set Interface
# Lock Key...:
#
#   Settings Lock -- the window stays fully usable (uploads, Serial
#   Monitor, viewing logs, adding/duplicating devices all keep working)
#   but editing anything that changes what gets flashed and to where --
#   ports, chip/flash settings, the firmware list, Batch Edit, Assign
#   Firmware Set, Firmware Profiles, and deleting devices -- is disabled.
#   Meant for a bench that's handed to less-trusted operators who should
#   only be able to run the flashing job already configured for them, not
#   reconfigure it.
#
#   Full Lock -- freezes the ENTIRE window behind an opaque overlay (see
#   app/ui/lock_overlay.py); nothing is reachable, including Upload/
#   Cancel, until the same key is re-entered. Meant for walking away from
#   a running batch on a bench PC.
ASSIGN_FIRMWARE_SET_SHORTCUT = "Ctrl+Shift+A"
INTERFACE_LOCK_SHORTCUT = "Ctrl+Shift+L"
FACTORY_MODE_LOCK_SHORTCUT = "Ctrl+Shift+F"

SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH = "interface_lock_key_hash"

# --------------------------------------------------------------------------
# User-customisable keyboard shortcuts (app/utilities/shortcuts.py)
# --------------------------------------------------------------------------
# Every entry the user is allowed to remap, keyed by a stable action id, with
# its default key sequence and a human-readable label for the Shortcuts
# dialog. Anything NOT listed here (e.g. a toolbar-only duplicate action)
# keeps a fixed, non-customisable shortcut.
DEFAULT_SHORTCUTS: dict[str, str] = {
    "new_project": "Ctrl+N",
    "open_project": "Ctrl+O",
    "save_project": "Ctrl+S",
    "save_project_as": "Ctrl+Shift+S",
    "exit_app": "Ctrl+Q",
    "add_device": "Ctrl+D",
    "batch_edit": "Ctrl+B",
    "assign_firmware_set": ASSIGN_FIRMWARE_SET_SHORTCUT,
    "upload_selected": "F5",
    "upload_all": "Ctrl+F5",
    "cancel_all": "Esc",
    "toggle_theme": "Ctrl+T",
    "lock_interface": INTERFACE_LOCK_SHORTCUT,
    "factory_mode_lock": FACTORY_MODE_LOCK_SHORTCUT,
    "open_serial_monitor": "Ctrl+M",
}

SHORTCUT_LABELS: dict[str, str] = {
    "new_project": "New Project",
    "open_project": "Open Project...",
    "save_project": "Save Project",
    "save_project_as": "Save Project As...",
    "exit_app": "Exit",
    "add_device": "Add Device",
    "batch_edit": "Batch Edit...",
    "assign_firmware_set": "Assign Firmware Set to Devices...",
    "upload_selected": "Upload Selected",
    "upload_all": "Upload All",
    "cancel_all": "Cancel All",
    "toggle_theme": "Toggle Dark/Light Theme",
    "lock_interface": "Full Lock",
    "factory_mode_lock": "Settings Lock",
    "open_serial_monitor": "Open Serial Monitor...",
}

SETTINGS_KEY_CUSTOM_SHORTCUTS = "custom_shortcuts"

# --------------------------------------------------------------------------
# Serial Monitor (app/ui/serial_monitor.py)
# --------------------------------------------------------------------------
DEFAULT_SERIAL_MONITOR_BAUD = 115200
SERIAL_MONITOR_LINE_ENDINGS = ["None", "\\n (LF)", "\\r\\n (CRLF)", "\\r (CR)"]

# --------------------------------------------------------------------------
# Flash Encryption / Secure Boot provisioning
# (app/flash_engine/security_manager.py, app/ui/security_settings_widget.py)
# --------------------------------------------------------------------------
# Everything here is a thin passthrough to `espsecure`/`espefuse` (both part
# of the official `esptool` PyPI package) -- no cryptographic or eFuse
# protocol logic lives in this app. See security_manager.py's module
# docstring for the full command mapping.

KEY_SOURCE_GENERATE = "generate"
KEY_SOURCE_EXISTING = "existing"
KEY_SOURCE_OPTIONS = [KEY_SOURCE_GENERATE, KEY_SOURCE_EXISTING]
KEY_SOURCE_LABELS = {
    KEY_SOURCE_GENERATE: "Generate a new key",
    KEY_SOURCE_EXISTING: "Use an existing key file",
}
DEFAULT_KEY_SOURCE = KEY_SOURCE_GENERATE

SECURE_BOOT_VERSIONS = ["1", "2"]
DEFAULT_SECURE_BOOT_VERSION = "2"
SECURE_BOOT_SCHEMES = ["rsa3072", "ecdsa192", "ecdsa256", "ecdsa384"]
DEFAULT_SECURE_BOOT_SCHEME = "rsa3072"

# Chips using the legacy (pre-"unified eFuse table") espefuse command shape,
# where `burn-key <BLOCK> <KEYFILE>` takes a fixed purpose name baked into
# the block itself (flash_encryption / secure_boot_v1 / secure_boot_v2)
# rather than a separate --keypurpose argument. Every other chip esptool
# supports uses the newer BLOCK_KEYn + explicit key-purpose scheme. Kept as
# a simple set here (not queried dynamically like SUPPORTED_CHIPS) because
# espefuse itself -- not esptool -- draws this line, and it has been stable
# across every 5.x release; SecurityCommandBuilder falls back to the
# unified-scheme shape for any chip not listed here, which is also correct
# for brand-new chip targets a newer esptool/espefuse adds.
LEGACY_EFUSE_CHIPS = {"esp32"}

# espefuse burn-key purposes for chips on the unified eFuse table scheme.
UNIFIED_KEY_PURPOSE_FLASH_ENCRYPTION = "XTS_AES_256_KEY"
UNIFIED_KEY_PURPOSE_SECURE_BOOT_V2 = "SECURE_BOOT_DIGEST0"
# espefuse block names, legacy scheme (ESP32 only).
LEGACY_BLOCK_FLASH_ENCRYPTION = "flash_encryption"
LEGACY_BLOCK_SECURE_BOOT_V1 = "secure_boot_v1"
LEGACY_BLOCK_SECURE_BOOT_V2 = "secure_boot_v2"
# Default unified-scheme key block. Devices that already used BLOCK_KEY0 for
# something else need a different block -- exposed as an editable field, not
# hardcoded further than this default.
DEFAULT_UNIFIED_KEY_BLOCK = "BLOCK_KEY0"

FLASH_ENCRYPTION_MODE_DEVELOPMENT = "development"
FLASH_ENCRYPTION_MODE_RELEASE = "release"
FLASH_ENCRYPTION_MODES = [FLASH_ENCRYPTION_MODE_DEVELOPMENT, FLASH_ENCRYPTION_MODE_RELEASE]
FLASH_ENCRYPTION_MODE_LABELS = {
    FLASH_ENCRYPTION_MODE_DEVELOPMENT: "Development (re-flashing plaintext images stays possible)",
    FLASH_ENCRYPTION_MODE_RELEASE: "Release (locks down re-flashing -- irreversible)",
}
DEFAULT_FLASH_ENCRYPTION_MODE = FLASH_ENCRYPTION_MODE_DEVELOPMENT

# Typed confirmation phrase required (in addition to a checkbox) before any
# eFuse-burning operation is allowed to run, since burning eFuses on real
# hardware is a one-way, irreversible operation -- see
# app/ui/provision_confirm_dialog.py.
PROVISION_CONFIRM_PHRASE = "BURN EFUSES"

STATUS_GENERATING_KEY = "Generating Key"
STATUS_SIGNING = "Signing"
STATUS_BURNING = "Burning eFuses"
STATUS_READING = "Reading"

STATUS_COLORS.update({
    STATUS_GENERATING_KEY: "#5b8def",
    STATUS_SIGNING: "#5b8def",
    STATUS_BURNING: "#e03131",
    STATUS_READING: "#5b8def",
})

# settings.json keys for Read Flash / eFuse / Chip Info output defaults --
# mirrors SETTINGS_KEY_MERGE_DEFAULT_LOCATION's "blank == ask every time /
# same folder as last used" pattern rather than a fixed baked-in path.
SETTINGS_KEY_READ_DEFAULT_LOCATION = "read_default_location"

# --------------------------------------------------------------------------
# Read Flash / Read eFuse / Chip Info (app/ui/read_device_dialog.py)
# --------------------------------------------------------------------------
READ_MODE_CHIP_INFO = "chip_info"
READ_MODE_FLASH_ID = "flash_id"
READ_MODE_EFUSE_SUMMARY = "efuse_summary"
READ_MODE_SECURITY_INFO = "security_info"
READ_MODE_READ_FLASH = "read_flash"

READ_MODE_LABELS = {
    READ_MODE_CHIP_INFO: "Chip Info",
    READ_MODE_FLASH_ID: "Flash ID",
    READ_MODE_EFUSE_SUMMARY: "eFuse Summary",
    READ_MODE_SECURITY_INFO: "Security Info (encryption / secure boot state)",
    READ_MODE_READ_FLASH: "Read Flash Region...",
}

# Default region read back by "Read Flash Region..." when the user hasn't
# entered their own address/size -- the first 4KB, covering the bootloader
# on chips that place it at the conventional 0x1000 address.
DEFAULT_READ_FLASH_ADDRESS = "0x0"
DEFAULT_READ_FLASH_SIZE = "0x1000"
