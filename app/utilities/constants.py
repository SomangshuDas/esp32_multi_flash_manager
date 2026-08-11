"""
constants.py
============
Central location for every "magic value" used across the application.
Keeping these in one module avoids scattering literals across the codebase
and makes future firmware/chip support trivial to extend.
"""

from __future__ import annotations

APP_NAME = "ESP32 Multi Flash Manager"
APP_VERSION = "0.3.0"
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

DEFAULT_BAUD = 921600
DEFAULT_FLASH_MODE = "dio"
DEFAULT_FLASH_FREQ = "40m"
DEFAULT_FLASH_SIZE = "4MB"
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
