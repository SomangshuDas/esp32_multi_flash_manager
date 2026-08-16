# Developer Documentation — ESP32 Multi Flash Manager

This document is for engineers extending or maintaining the codebase.

## 1. Design principles

1. **Strict MVC.** `app/models` contains plain dataclasses with zero Qt
   imports — they're trivially unit-testable and JSON-serializable.
   `app/controllers` are `QObject`s that own no widgets, only emit Qt
   `Signal`s and expose plain methods. `app/ui` widgets only ever call
   controller methods and connect to controller signals — they never call
   into `flash_engine`, `project_manager`, `firmware_manager`, or
   `device_manager` directly.
2. **Out-of-process flashing.** `esptool` is invoked as a subprocess
   (`python -m esptool ...`), never imported and called in-process. This
   isolates the GUI from esptool's `sys.exit()` calls and `\r`-based
   progress printing, and lets us kill a stuck flash cleanly. See
   `app/flash_engine/esptool_wrapper.py`.
3. **One QThread per device during a batch.** `FlashWorker` (in
   `app/workers/flash_worker.py`) is a `QThread` subclass; `N` devices
   selected for upload means `N` concurrently running `FlashWorker`
   instances, each with its own subprocess. This is what gives real
   parallelism without any manual thread-pool bookkeeping — `FlashController`
   just launches one `FlashWorker` per device and aggregates their
   `finished_flash` signals to know when the whole batch is done.
4. **Never crash.** `app/main.py` installs a global `sys.excepthook` that
   logs any unhandled exception to `error.log` and shows a message box,
   instead of letting Qt/Python kill the process silently. Additionally,
   `FlashWorker.run()` wraps its entire body in a broad `except Exception`
   so a single device's failure can never propagate and kill other
   in-flight workers or the UI thread.
5. **Everything persists through plain JSON**, not pickle — `.efmproj`
   project files and firmware profile files are both readable/diffable/
   editable by hand if needed, which matters a lot in a manufacturing
   environment where configs get checked into version control or emailed
   around.

## 2. Module map

| Module | Responsibility |
|---|---|
| `app/models/device_model.py` | `DeviceConfig` (persisted config) + `DeviceRuntimeState` (transient progress/status, not persisted) |
| `app/models/firmware_model.py` | `FirmwareEntry`: one `.bin` + address + computed MD5/size/missing-flag |
| `app/models/project_model.py` | `ProjectModel`: the full save-file contents |
| `app/models/history_model.py` | `HistoryEntry` + CSV export helper |
| `app/controllers/device_controller.py` | CRUD + search + batch-edit over the device list |
| `app/controllers/flash_controller.py` | Spins up/tracks `FlashWorker`s, aggregates batch completion, emits history entries |
| `app/controllers/project_controller.py` | New/open/save/save-as, missing-firmware detection on load |
| `app/flash_engine/esptool_wrapper.py` | `FlashCommandBuilder` (DeviceConfig → argv) + `FlashProcess` (subprocess wrapper) + `parse_progress_line` |
| `app/flash_engine/validator.py` | Pure, offline pre-upload validation → `ValidationReport` |
| `app/project_manager/project_io.py` | `.efmproj` JSON I/O + recent-projects list (QSettings) |
| `app/device_manager/port_scanner.py` | pyserial wrapper: `list_available_ports()` |
| `app/firmware_manager/auto_detect.py` | Folder → `list[FirmwareEntry]` with known-address assignment |
| `app/firmware_manager/profiles.py` | Named, reusable firmware+settings bundles, stored as JSON in app-data |
| `app/workers/flash_worker.py` | `QThread` that drives one device's `esptool` subprocess |
| `app/workers/port_watcher.py` | `QTimer`-polled COM port connect/disconnect detection |
| `app/logging_setup/logger.py` | Rotating file handlers: application/flash/error/debug logs |
| `app/utilities/constants.py` | Every shared literal (chip lists, baud rates, status strings, colors, shortcuts, settings keys, ...) |
| `app/utilities/helpers.py` | Pure functions: MD5, human-readable sizes/durations, hex address validation, ... |
| `app/utilities/update_checker.py` | GitHub Releases polling + portable-vs-installer asset selection (`is_portable_build()`) |
| `app/utilities/shortcuts.py` | User-customisable keyboard shortcuts: defaults + `AppSettings` overrides + duplicate detection |
| `app/ui/lock_overlay.py` | `LockOverlay`: the full-window "Interface Locked" widget used by Tools → Lock Interface |
| `app/ui/serial_monitor.py` | `SerialMonitorWidget` + background `_SerialReaderThread`: standalone, multi-port live serial console |
| `app/ui/shortcuts_dialog.py` | `ShortcutsDialog`: remap every customisable shortcut, with live duplicate-conflict warnings |
| `app/ui/*.py` | Qt widgets/dialogs — see file docstrings for each |

## 3. Extending chip / flash-parameter support

All valid choices for chip type, baud rate, flash mode/frequency/size live
in `app/utilities/constants.py` as plain lists — add a value there and it
automatically appears in every relevant dropdown (`DeviceSettingsWidget`,
`BatchEditDialog`) and the validator's allow-list. No other file needs to
change unless the new chip requires a different `esptool` command-line
flag shape, in which case extend `FlashCommandBuilder` in
`esptool_wrapper.py`.

## 4. Adding a new device setting

1. Add the field (with a sensible default) to `DeviceConfig` in
   `app/models/device_model.py`, and to its `to_dict`/`from_dict`.
2. Add a widget for it in `DeviceSettingsWidget`
   (`app/ui/device_settings_widget.py`), wire its change signal to
   `_commit`, and read/write it in `set_device`/`_commit`.
3. If it should be flashable via `esptool`, add the corresponding flag in
   `FlashCommandBuilder.build_write_flash_args`.
4. If it should be batch-editable, add an entry to `_FIELDS` in
   `app/ui/batch_edit_dialog.py`.
5. If it should be validated, add a check in
   `app/flash_engine/validator.py`.

## 5. Adding a new panel / dock

Follow the pattern in `app/ui/history_panel.py`: a self-contained
`QWidget` subclass that exposes whatever signals it needs and is wired up
inside `MainWindow._wire_signals()`. Add it to the main window with
`QDockWidget` (see `_build_ui`) if it should be dockable/toggleable from
the View menu.

## 6. Plugin architecture (extension point)

The codebase is deliberately organized so a plugin system can be added
without restructuring: `MainWindow._wire_signals()` and `_build_ui()` are
the two points where new panels/behaviors are attached. A future
`app/plugins/` package could expose a `Plugin` protocol
(`register(main_window: MainWindow) -> None`) and have `main.py` discover
and call `register()` for each plugin found in a `plugins/` folder next to
the executable, before `window.show()`. Because every cross-cutting
capability (device list, firmware list, flashing, project I/O) is already
exposed via controller signals/methods rather than being buried in
private widget state, a plugin can hook into any of them without needing
access to widget internals.

## 7. Testing

There is no bundled test suite in this deliverable, but the architecture
is test-friendly:

- `app/models`, `app/flash_engine/validator.py`,
  `app/firmware_manager/auto_detect.py`, and `app/utilities/helpers.py`
  have zero Qt dependency and can be tested with plain `pytest`.
- `app/controllers` can be tested by constructing them directly (they're
  `QObject`s but don't need a running event loop for their plain methods
  — only their signals need `QApplication` to exist, which `pytest-qt`
  handles).
- UI smoke-testing can run headlessly by setting
  `QT_QPA_PLATFORM=offscreen` before importing `PySide6`.

Recommended additions for a production fork: `pytest` + `pytest-qt`,
plus a `tests/` folder mirroring the `app/` package layout.

## 8. Logging

Four rotating log files (5 MB × 5 backups each) live under the per-OS
application-data directory returned by
`app/utilities/helpers.py::get_app_data_dir`:

| OS | Log directory |
|---|---|
| Windows | `%APPDATA%\ESP32MultiFlashManager\logs\` |
| macOS | `~/Library/Application Support/ESP32MultiFlashManager/logs/` |
| Linux | `$XDG_DATA_HOME/ESP32MultiFlashManager/logs/` (or `~/.local/share/ESP32MultiFlashManager/logs/` if `XDG_DATA_HOME` is unset) |

- `application.log` — INFO+ from anywhere
- `flash.log` — DEBUG+ but filtered to `app.flash_engine.*` /
  `app.workers.*` loggers only
- `error.log` — ERROR+ from anywhere
- `debug.log` — everything, unfiltered

Get a logger anywhere with `from app.logging_setup.logger import
get_logger; logger = get_logger(__name__)`. `Settings → Open Logs Folder`
in the app opens this directory directly on any OS via
`QDesktopServices.openUrl`.

## 9. Cross-platform notes

- **App-data / settings / logs**: `get_app_data_dir()` resolves to the
  correct native location per OS (see the table above) rather than a
  single Windows-shaped fallback — check that function first if you ever
  need to add another persisted file.
- **Bundled resources (icons, themes)**: always resolve paths through
  `resource_path()` in `app/utilities/helpers.py` instead of hardcoding
  `"resources/..."`. It transparently handles PyInstaller's `sys._MEIPASS`
  redirection so the same code works running from source and from a
  frozen build on any OS.
- **Serial ports**: `device_manager/port_scanner.py` wraps `pyserial`,
  which already abstracts `COMx` (Windows) vs `/dev/ttyUSBx` /
  `/dev/cu.usbserial-*` (Linux/macOS) naming — no OS branching is needed
  in application code for port discovery.
- **`esptool` subprocess launch**: `flash_engine/esptool_wrapper.py` only
  branches on `sys.platform` once, to set `subprocess.CREATE_NO_WINDOW` on
  Windows (there is no equivalent flag needed on macOS/Linux).
- **CI**: `.github/workflows/build.yml` builds and smoke-tests the app on
  `windows-latest`, `macos-latest`, and `ubuntu-latest` on every push, so a
  platform regression is caught before it reaches a release.

## 10. Known simplifications in this deliverable

For transparency: transfer-speed is a rough estimate (total enabled
firmware bytes ÷ elapsed time), not read from esptool's own byte-level
telemetry, since esptool does not expose that over a stable machine-
readable channel. ETA is derived from elapsed-time ÷ percent-complete,
which is accurate once erase/connect overhead is behind the device but
can be noisy in the first few seconds. The **Tools → Check for
Updates...** menu item is fully wired up: it queries the GitHub
Releases API for `GITHUB_REPO` (see `app/utilities/constants.py`),
compares the latest tag against `APP_VERSION`, and — if a newer
release exists — offers to open the browser straight to the release
asset matching both the current OS *and* the current build kind
(portable vs. installer, via `update_checker.is_portable_build()`). The
app never downloads or applies an update in place; installing is always
left to the OS-native installer/DMG/AppImage flow.

## 11. Assign Firmware Set to Devices, Serial Monitor & Interface Lock

`Devices → Assign Firmware Set to Devices...`
(`MainWindow._on_assign_firmware_set`) stamps one imported firmware
folder across many devices in one step: it reuses
`firmware_manager.auto_detect.scan_firmware_folder()` for the scan and
`DeviceController.apply_firmware_to_devices()` for the assignment,
which gives each target device its own `FirmwareEntry.duplicate()`s so
later per-device address edits never cross-contaminate another
device's copy. `_choose_assign_firmware_targets()` asks explicitly
whether to apply to **All Devices** or just the current **Selected
Devices** (the latter option is only offered when something is
selected) via a `QMessageBox` with named buttons rather than an
ambiguous Yes/No.

**Serial Monitor** (`app/ui/serial_monitor.py::SerialMonitorWidget`,
`Tools → Open Serial Monitor...` or right-click a device row) is
independent of the flashing pipeline entirely -- it opens its own
`pyserial` connection on a background `_SerialReaderThread` (QThread)
so the GUI never blocks on I/O, and supports any number of concurrent
ports, each tracked by `MainWindow._serial_monitors: dict[str,
SerialMonitorWidget]` keyed by port name (opening the same port twice
just raises the existing window). `MainWindow._busy_ports()` refuses to
open a monitor on a port that's mid-upload; conversely,
`flash_engine.validator.validate_devices()`'s new `monitor_ports`
parameter (populated from `MainWindow._monitor_ports()`, i.e. only
*connected* monitors) refuses to start an upload on a port that
already has a Serial Monitor open, and reports which one to close.

**Interface Lock** (`Tools → Lock Interface`) disables
the menu bar, every toolbar, every dock widget, the central widget, and
every `QAction` created via `MainWindow._add_action` (tracked in
`self._all_actions` — disabling the container widgets alone does not
stop a `QAction`'s window-level keyboard shortcut from still firing), and
raises `app/ui/lock_overlay.py::LockOverlay` on top of the whole window.
Before any of that, `_on_lock_interface()` calls
`_open_secondary_window_titles()` to check for any visible Logs or
Serial Monitor window (both are independent top-level widgets outside
`centralWidget()`, so disabling the central widget alone would leave
them live); if any are open, locking is refused and the user is told
which window(s) to close first. The unlock key is never stored in
plaintext: `Tools → Set Interface Lock Key...` hashes it with SHA-256
(`hashlib.sha256`) before writing it to `AppSettings` under
`SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH`, and `_on_unlock_attempt()`
compares hashes. `closeEvent()` refuses to close the window while
`lock_overlay.isVisible()`, so the lock can't be bypassed with the OS
window-manager's close button.

## 12. Keyboard shortcut customisation

Every customisable action has a stable `action_id` (see
`app.utilities.constants.DEFAULT_SHORTCUTS` /
`SHORTCUT_LABELS`) instead of a shortcut baked directly into
`MainWindow._add_action()`'s call site. `app/utilities/shortcuts.py`
merges those defaults with any user overrides saved under
`AppSettings`' `SETTINGS_KEY_CUSTOM_SHORTCUTS` (only the entries that
differ from default are persisted, so a future default change is
picked up automatically for anyone who never touched that shortcut).
`Tools → Keyboard Shortcuts...` opens `app/ui/shortcuts_dialog.py`'s
`ShortcutsDialog`, one `QKeySequenceEdit` per action; `find_duplicates()`
re-runs on every edit and blocks Save (greys out OK, shows the
conflicting actions) until every key sequence is unique. On accept,
`MainWindow` re-applies every shortcut live via
`self._shortcut_actions: dict[str, QAction]` — no menu rebuild needed.
Actions without an `action_id` (e.g. a toolbar-only duplicate of a menu
action) keep a fixed, non-customisable shortcut.

---

Author: Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
