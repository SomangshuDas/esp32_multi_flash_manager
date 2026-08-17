"""
constants.py
============
Central location for every "magic value" used across the application.
Keeping these in one module avoids scattering literals across the codebase
and makes future firmware/chip support trivial to extend.
"""

from __future__ import annotations

APP_NAME = "ESP32 Multi Flash Manager"
APP_VERSION = "0.6.1"
ORG_NAME = "Somangshu Das"

# --------------------------------------------------------------------------
# Chip / flashing parameter choices (mirrors what esptool.py itself accepts)
# --------------------------------------------------------------------------
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
# Interface Lock (app/ui/main_window.py)
# --------------------------------------------------------------------------
ASSIGN_FIRMWARE_SET_SHORTCUT = "Ctrl+Shift+A"
INTERFACE_LOCK_SHORTCUT = "Ctrl+Shift+L"

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
    "lock_interface": "Lock Interface",
    "open_serial_monitor": "Open Serial Monitor...",
}

SETTINGS_KEY_CUSTOM_SHORTCUTS = "custom_shortcuts"

# --------------------------------------------------------------------------
# Serial Monitor (app/ui/serial_monitor.py)
# --------------------------------------------------------------------------
DEFAULT_SERIAL_MONITOR_BAUD = 115200
SERIAL_MONITOR_LINE_ENDINGS = ["None", "\\n (LF)", "\\r\\n (CRLF)", "\\r (CR)"]
