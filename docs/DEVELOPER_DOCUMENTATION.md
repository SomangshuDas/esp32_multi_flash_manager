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
   `app/flash_engine/esptool_wrapper.py`. `FlashProcess` drains the
   subprocess's stdout on its own background thread into a queue rather
   than iterating it directly from the QThread, so `FlashWorker` can poll
   with a timeout (`FLASH_STALL_TIMEOUT_SECONDS`, currently 45s) instead
   of blocking forever — a device that disconnects mid-write can leave
   the OS serial driver parked in an uninterruptible I/O wait that
   esptool has no timeout for, and without this the worker's QThread
   (and therefore `FlashController.is_busy()`) never returns.
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
| `app/flash_engine/validator.py` | Pure, offline pre-upload validation (duplicate/invalid/overlapping addresses, port availability, etc.) → `ValidationReport` |
| `app/project_manager/project_io.py` | `.efmproj` JSON I/O + recent-projects list (QSettings) |
| `app/device_manager/port_scanner.py` | pyserial wrapper: `list_available_ports()` |
| `app/firmware_manager/auto_detect.py` | Folder → `list[FirmwareEntry]` with known-address assignment |
| `app/firmware_manager/profiles.py` | Named, reusable firmware+settings bundles, stored as JSON in app-data |
| `app/workers/flash_worker.py` | `QThread` that drives one device's `esptool` subprocess |
| `app/workers/port_watcher.py` | `QTimer`-polled COM port connect/disconnect detection |
| `app/logging_setup/logger.py` | Rotating file handlers: application/flash/error/debug logs |
| `app/utilities/constants.py` | Every shared literal (fallback chip list, baud rates, status strings, colors, shortcuts, settings keys, merge/theme/lock constants, ...) |
| `app/utilities/chip_detect.py` | Dynamic chip-support detection from the installed `esptool` package (`detect_supported_chips()`), plus `find_unsupported_chips()` for the project-load warning |
| `app/utilities/helpers.py` | Pure functions: MD5, human-readable sizes/durations, hex address validation, ... |
| `app/utilities/update_checker.py` | GitHub Releases polling + portable-vs-installer asset selection (`is_portable_build()`) |
| `app/utilities/shortcuts.py` | User-customisable keyboard shortcuts: defaults + `AppSettings` overrides + duplicate detection |
| `app/firmware_manager/bin_merge.py` | Merge Bins: pre-merge validation (`validate_merge_entries`) + running `esptool merge-bin` (`run_merge`) |
| `app/flash_engine/security_manager.py` | `SecurityCommandBuilder` (`DeviceConfig` → `espsecure`/`espefuse` argv) + offline key-gen/signing runners + `validate_security_settings()` + `parse_security_state_from_output()` |
| `app/workers/security_worker.py` | `ProvisionWorker`: `QThread` that generates any requested keys then burns the requested eFuses for one device |
| `app/workers/read_worker.py` | `ReadWorker`: `QThread` for the read-only Chip Info / Flash ID / eFuse Summary / Security Info / Read Flash Region operations |
| `app/ui/security_settings_widget.py` | `SecuritySettingsWidget`: the Security tab — per-device flash encryption/secure boot fields, commit-on-change, opens `ProvisionDialog` |
| `app/ui/provision_dialog.py` | `ProvisionDialog`: validation → `ProvisionConfirmDialog` → runs `ProvisionWorker` with a live log |
| `app/ui/provision_confirm_dialog.py` | `ProvisionConfirmDialog`: checkbox + typed-phrase confirmation gate shown before any eFuse burn |
| `app/ui/read_device_dialog.py` | `ReadDeviceDialog`: the Read Flash / eFuse / Chip Info panel, opened from Tools menu or the device table's context menu |
| `app/ui/merge_bin_dialog.py` | `MergeBinDialog`: pick source firmware, validate, merge, choose the post-merge Firmware Settings action |
| `app/ui/lock_overlay.py` | `LockOverlay`: the full-window "Interface Locked" widget used by Tools → Lock Interface → Full Lock |
| `app/ui/serial_monitor.py` | `SerialMonitorWidget` + background `_SerialReaderThread`: standalone, multi-port live serial console |
| `app/ui/shortcuts_dialog.py` | `ShortcutsDialog`: remap every customisable shortcut, with live duplicate-conflict warnings |
| `app/ui/*.py` | Qt widgets/dialogs — see file docstrings for each |

## 3. Extending chip / flash-parameter support

**Chip type is no longer a hardcoded list.** At startup, `MainWindow`
calls `app.utilities.chip_detect.detect_supported_chips()`, which imports
`esptool.targets.CHIP_LIST` from the installed `esptool` package directly
— so a newer esptool that adds a chip target shows up in every chip
dropdown (`DeviceSettingsWidget`, `BatchEditDialog`, `MergeBinDialog`) and
the validator's allow-list automatically, with no code change here. The
`SUPPORTED_CHIPS` list in `constants.py` is now only the last-resort
fallback used if that dynamic import fails (broken/missing esptool
install) — don't rely on it being current.

Baud rate and flash mode/frequency/size are still plain lists in
`app/utilities/constants.py` — add a value there and it automatically
appears in every relevant dropdown and the validator's allow-list. No
other file needs to change unless the new chip/parameter requires a
different `esptool` command-line flag shape, in which case extend
`FlashCommandBuilder` in `esptool_wrapper.py` (also used by
`bin_merge.py` for `merge-bin`).

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
`_busy_ports()` is keyed off `FlashController.is_busy()` (a live,
running `FlashWorker`), so the stall-timeout watchdog described above is
also what guarantees this check can't stay permanently "busy" against a
device that silently disconnected -- previously a hung worker never
finished, so `is_busy()` stayed `True` forever and Serial Monitor
refused to open on that port until the app was restarted.

**Busy-device guards.** A device whose `runtime.status` is currently in
`ACTIVE_STATUSES` (i.e. `FlashController.is_busy(device.id)` is `True`)
cannot be removed (`MainWindow._on_remove_devices` filters busy ids out
of the selection and warns instead of silently skipping them) and its
`DeviceSettingsWidget` is put into a read-only "locked" state
(`DeviceSettingsWidget.set_locked()`, driven from
`MainWindow._on_status_changed`/`_on_device_selected`) so its
com_port/chip/baud/etc. fields can't be edited out from under the
`FlashWorker` currently reading that same `DeviceConfig`. This
intentionally does *not* extend to that device's Live Output window or
an open Serial Monitor on its port -- neither of those touches
`runtime.status`, so both remain fully interactive during an upload. The
same guard extends to bulk reconfiguration: `MainWindow._exclude_busy_devices()`
is called by `_on_batch_edit`, `_on_assign_firmware_set`, and
`_on_open_profiles` before touching any device, filtering out (and
warning about) any target that's mid-upload rather than silently
rewriting settings out from under a running `FlashWorker`. Saving the
project itself is never restricted by any of this.

**Interface Lock has two independent modes, grouped under `Tools → Lock
Interface`**, both gated behind the same key (hashed with
`hashlib.sha256` under `AppSettings`' `SETTINGS_KEY_INTERFACE_LOCK_KEY_HASH`,
set via `Tools → Set Interface Lock Key...`):

- **Settings Lock** (`Tools → Lock Interface → Settings Lock`,
  `MainWindow._on_toggle_factory_lock` /
  `_set_factory_mode_locked`) is a *lighter*, non-freezing lock: the
  window stays fully interactive (uploads, Serial Monitor, viewing logs
  keep working) but `FirmwarePanel.set_factory_locked()`,
  `DeviceSettingsWidget.set_factory_locked()`, and
  `DevicePanel.set_deletion_locked()` disable the firmware list (Merge
  Bins included), all port/chip/flash-setting fields, and deleting
  devices, and `self._factory_lock_actions` (Batch Edit, Assign Firmware
  Set, Firmware Profiles) are disabled at the `QAction` level too.
  Unlocking re-prompts for the key via `QInputDialog` — there's no
  overlay for this mode since the rest of the window is meant to stay
  usable.
- **Full Lock** (`Tools → Lock Interface → Full Lock`,
  `MainWindow._on_lock_interface` — the original "Lock
  Interface" behaviour, moved into this submenu now that there are two
  lock modes) disables the menu bar, every toolbar, every dock widget, the
  central widget, and every `QAction` created via `MainWindow._add_action`
  (tracked in `self._all_actions` — disabling the container widgets alone
  does not stop a `QAction`'s window-level keyboard shortcut from still
  firing), and raises `app/ui/lock_overlay.py::LockOverlay` on top of the
  whole window. Before any of that, `_on_lock_interface()` calls
  `_open_secondary_window_titles()` to check for any visible Logs or
  Serial Monitor window (both are independent top-level widgets outside
  `centralWidget()`, so disabling the central widget alone would leave
  them live); if any are open, locking is refused and the user is told
  which window(s) to close first. `_on_unlock_attempt()` compares key
  hashes the same way. `closeEvent()` refuses to close the window while
  `lock_overlay.isVisible()`, so the lock can't be bypassed with the OS
  window-manager's close button.

Both modes can be combined (Settings Lock active, then Full Lock on top);
each is unlocked independently with the same key.

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

## 13. System Default theme

`app/utilities/constants.THEME_OPTIONS` is `["system", "dark", "light"]`,
with `"system"` as `DEFAULT_THEME`. `"system"` is not itself a stylesheet
— `app/ui/theme.py::resolve_theme()` turns it into a concrete `"dark"`/
`"light"` choice by asking Qt for the OS's current color scheme via
`QGuiApplication.styleHints().colorScheme()` (needs Qt 6.5+, comfortably
covered by this project's `PySide6>=6.6.0` requirement); `stylesheet_for()`
calls `resolve_theme()` internally so it always returns a real stylesheet
even if handed `"system"` directly. `AppSettings` stores the *preference*
as entered (including the literal string `"system"`), never the resolved
value, so a later OS theme change is picked up automatically.

Live detection while the app is running is `MainWindow._connect_system_theme_watcher()`,
which connects `QGuiApplication.styleHints().colorSchemeChanged` to
`_on_system_theme_changed()`; that handler re-applies the theme (which
re-resolves `"system"`) only when `"system"` is the currently active
preference, so it's a no-op if the user has explicitly picked Dark or
Light. `View → Toggle Dark/Light Theme` (`MainWindow._toggle_theme`) is
unchanged from before this feature: it flips between explicit Dark and
Light only. Picking **System Default** is done from the Settings dialog's
theme dropdown; the toggle shortcut is a fast way to step away from
System Default to a specific theme without opening Settings.

## 14. Bin Merge

`app/firmware_manager/bin_merge.py` implements "Merge Bins": combining a
device's separate firmware images into one flashable `.bin` via esptool's
own `merge-bin` command (offline — no port/board needed, unlike
write-flash). Two pieces:

- `validate_merge_entries(entries, chip, output_path) -> MergeReport` —
  the same category of pre-flight checks as
  `flash_engine/validator.py`'s pre-upload validation (missing files,
  invalid/duplicate addresses, byte-range overlaps via a sort-and-compare-
  neighbours pass, plus merge-specific checks: no chip selected, "auto"
  selected instead of a concrete chip, bad/unwritable output path).
  `MergeIssue`/`MergeSeverity` mirror `validator.py`'s `ValidationIssue`/
  `Severity` pattern but are deliberately a separate, lighter type (no
  `device_name` field — a merge isn't scoped to one device's validation
  report).
- `run_merge(entries, chip, output_path, ...) -> MergeResult` — builds the
  command via `FlashCommandBuilder.build_merge_bin_args()` (new method,
  same builder flashing already uses) and runs it with a **synchronous**
  `subprocess.run()`, deliberately *not* a `QThread`/`FlashWorker` the way
  flashing is — merging is fast, local, and CPU/disk-bound, not a
  multi-minute serial transfer, so blocking the calling thread briefly
  (with a wait cursor, handled by the dialog) is the simpler and correct
  choice here.

`app/ui/merge_bin_dialog.py::MergeBinDialog` is the UI: a checkbox-per-row
table of the device's firmware, a **Target Chip** dropdown (populated from
the same dynamically-detected chip list as everywhere else, "auto"
excluded since merge-bin needs a concrete chip), an output path field
defaulting to `firmware_bin_folder()`'s result (the folder containing a
file literally named `firmware.bin`, falling back to the first entry's
folder) joined with the Settings-configured default filename, a
**Validate** button, and an **After Merging** dropdown of the
`MERGE_POST_ACTION_*` constants (add+de-select / add+remove / add-only /
do-nothing), pre-selected from the Settings-configured default. On a
successful merge the dialog constructs a new `FirmwareEntry` at `0x0` (a
merged image already has every source file's offsets baked in — see
esptool's own `merge_bin()` docs — so it's always flashed starting at
0x0) and `accept()`s; `FirmwarePanel._open_merge_dialog()` reads
`merged_entry()`/`post_action()`/`source_entry_ids()` back and applies the
chosen post-merge action to the device's firmware list itself (add /
de-select / remove), so `bin_merge.py` and `MergeBinDialog` never mutate
`DeviceConfig` directly.

## 15. Flash Encryption / Secure Boot provisioning & Read Flash/eFuse/Chip Info

Both features are deliberately thin layers over the official `espsecure`
and `espefuse` command-line tools (both distributed inside the same
`esptool` PyPI package, as separate top-level importable packages —
`import espsecure` / `import espefuse`, not `esptool.espsecure`). Neither
this app nor these two modules implement any cryptographic primitive,
key-derivation, or eFuse wire-protocol logic; they only build argv lists
and run them, exactly the same pattern `FlashCommandBuilder`/`bin_merge.py`
already use for `esptool` itself. See `security_manager.py`'s module
docstring for the exact command each builder method maps to (this mapping
was verified against the actual installed `esptool==5.3.1` CLI's `--help`
output, not assumed from memory or older esptool releases — command names
changed to hyphenated Click-style verbs in esptool 5.x).

**Model:** `SecurityConfig` (on `DeviceConfig.security`) holds one
device's flash-encryption/secure-boot settings and is persisted in
`.efmproj` like every other `DeviceConfig` field.
`DeviceRuntimeState.flash_encryption_detected` /
`.secure_boot_detected` are transient, *not* persisted, `bool | None`
fields — `None` means "unknown / never read", populated only by an
explicit Security Info or eFuse Summary read (see below), and consumed by
`validator.py`'s pre-upload check for the "flashing plaintext firmware to
an already-encrypted device" foot-gun.

**Chip-family branching:** `is_legacy_efuse_chip(chip_type)` is the one
place that decides between espefuse's two eFuse-block addressing schemes
— the original ESP32's fixed block names (`flash_encryption`,
`secure_boot_v1`, `secure_boot_v2`) versus every other supported chip's
unified `BLOCK_KEYn` + explicit key-purpose scheme. `LEGACY_EFUSE_CHIPS`
in `constants.py` is intentionally a small hardcoded set (currently just
`{"esp32"}`) rather than something derived dynamically the way
`SUPPORTED_CHIPS` is — this split is drawn by `espefuse` itself, not by
esptool's per-chip target list, and has been stable across every 5.x
release.

**Provisioning flow (irreversible — burns real eFuses):**
`SecuritySettingsWidget` (the Security tab) edits `SecurityConfig` with
the same commit-on-change pattern as `DeviceSettingsWidget`, and its
**Provision Device (Burn eFuses)...** button opens `ProvisionDialog`,
which:

1. Runs `validate_security_settings()` and blocks on any error.
2. Shows `ProvisionConfirmDialog` — a checkbox **and** a typed
   confirmation phrase (`PROVISION_CONFIRM_PHRASE`, currently
   `"BURN EFUSES"`) are both required before this returns `True`. This is
   the actual UI-level confirmation the feature spec requires; only after
   it's accepted does the app pass `--do-not-confirm` to `espefuse` (that
   flag exists only to skip espefuse's own interactive terminal prompt,
   which would otherwise hang forever against this app's piped
   subprocess — it is not a substitute for this dialog).
3. Starts `ProvisionWorker` (`QThread`), which generates any requested
   keys offline (`generate_flash_encryption_key`/`generate_signing_key`,
   synchronous `subprocess.run()` since these finish in well under a
   second — same rationale as `bin_merge.run_merge()`), then burns each
   requested eFuse block by running `SecurityCommandBuilder`'s burn-*
   commands through `FlashProcess`, the same subprocess-streaming class
   `FlashWorker` uses for actual flashing.

**Read Flash / eFuse / Chip Info:** `ReadWorker` (`QThread`) plus
`ReadDeviceDialog` implement a read-only inspection panel independent of
the upload workflow — opened from Tools → Read Flash / eFuse / Chip
Info... (prompts for a device if more than one exists) or a single-row
context-menu entry on `DeviceTable`/`device_panel.py`
(`read_device_requested` signal). Five operations, each mapping straight
to one esptool/espefuse read-only command (`build_read_command()` in
`read_worker.py` is the single place mapping `READ_MODE_*` → command, kept
as a free function so the dialog can be unit-tested without spinning up a
thread): Chip Info (`chip-id`), Flash ID (`flash-id`), eFuse Summary
(`espefuse summary`), Security Info (`get-security-info`), and Read Flash
Region (`read-flash <addr> <size> <out>`). Output-file handling (Settings-
backed default folder, remembering the last-used folder,
`SETTINGS_KEY_READ_DEFAULT_LOCATION`) intentionally mirrors Merge Bins'
output-path field rather than introducing a new pattern.

A successful Security Info or eFuse Summary read is fed through
`parse_security_state_from_output()` — a best-effort, defensively-written
text scan (never a hard parse) that updates
`DeviceRuntimeState.flash_encryption_detected`/`.secure_boot_detected`
when it can confidently tell, and leaves them alone (not "False") when it
can't. This is what makes the "device already shows flash encryption
enabled" pre-upload/pre-provision warning possible without this app
implementing any eFuse-layout parsing of its own — read `espefuse`'s own
output.

**Frozen-build (PyInstaller) support:** `espsecure`/`espefuse` need the
exact same re-exec trick `esptool` already uses (see §9 /
`app/main.py`'s `_ESPTOOL_REEXEC_FLAG` handling) since `sys.executable` in
a frozen build is this app's own binary, not a real Python interpreter.
`ESPSECURE_REEXEC_FLAG`/`ESPEFUSE_REEXEC_FLAG` in `constants.py`,
`espsecure_command_prefix()`/`espefuse_command_prefix()` in
`esptool_wrapper.py`, and matching interception blocks in `main.py` mirror
the esptool ones exactly. Packaging (`packaging/*/`,
`.github/workflows/build.yml`, `.github/workflows/release.yml`) all pass
`--collect-all espsecure --collect-all espefuse` alongside the existing
`--collect-all esptool` — collecting `esptool` alone does **not** bundle
these, since they're separate top-level packages, not submodules.

---

Author: Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
