# ESP32 Multi Flash Manager

A production-grade, cross-platform desktop application for flashing
firmware onto an **unlimited number of ESP32 devices in parallel**, built
on top of the official [`esptool`](https://github.com/espressif/esptool)
backend (plus its `espsecure`/`espefuse` companion tools for flash
encryption, secure boot, and eFuse operations) for reliability.

It is designed for manufacturing/production-floor use, where an operator
may need to flash a bench of a dozen ESP32 boards at once, track results,
and keep an auditable history — well beyond what the Espressif Flash
Download Tool offers, while still relying on Espressif's own flashing
implementation for correctness.

**Author:** Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![PySide6](https://img.shields.io/badge/UI-PySide6%20(Qt)-41cd52)
![Cross Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Highlights

- **Unlimited devices, unlimited firmware files per device.** Each device
  has its own port, chip type, baud rate, flash mode/frequency/size, and
  boolean flags (erase / reset / compression / stub loader), plus
  a free-text custom-arguments field for power users.
- **True parallel flashing.** Every device you upload to gets its own
  worker thread and its own `esptool` subprocess — a slow or stuck board
  never blocks the others, and the UI never freezes.
- **Automatic firmware detection.** Point the app at a build output folder
  and it recognizes `bootloader.bin`, `partition-table.bin`,
  `ota_data_initial.bin`, `boot_app0.bin`, `firmware.bin`, etc. and assigns
  their standard flash addresses automatically. Unknown `.bin` files are
  still added, with an editable address.
- **Project files (`.efmproj`).** Save your whole bench configuration —
  every device, every firmware path, every flash setting, and your window
  layout — to a single JSON project file. Reopening a project with missing
  firmware never crashes; missing files are flagged and easy to relink.
- **Live serial port manager.** Ports are polled continuously; plugging or
  unplugging a board is reflected in the UI within ~2 seconds, on Windows
  COM ports as well as Linux/macOS `/dev/tty*` devices.
- **Per-device live console.** "View Log" opens the raw, unfiltered
  `esptool` output for that device, with pause/resume, search, copy, save,
  and clear.
- **Pre-upload validation.** Before anything is flashed, the app checks
  for duplicate ports, missing firmware files, invalid/duplicate flash
  addresses, missing bootloader/partition table, invalid flash modes, and
  invalid chip selections, and shows a report — errors block the upload.
- **Flash history + CSV export.** Every attempt (success, failure, or
  cancellation) is logged with date, time, device, firmware, and duration,
  and can be exported for QA/traceability records.
- **Firmware Profiles.** Save a device's firmware list + flash settings as
  a named, reusable profile (e.g. "ESP32 RFID Reader") and apply it to any
  device in one click.
- **Device templates / cloning.** Duplicate a fully-configured device
  instantly.
- **Batch editing.** Change one setting (baud rate, flash mode, erase
  flag, ...) across every device — or just the ones you've selected — in a
  single action.
- **Dashboard.** At-a-glance counts of total / connected / disconnected /
  ready / uploading / failed / completed devices.
- **Fully adjustable device table.** Every column — including Name — can
  be resized by dragging its header, so the table fits your workflow
  instead of a fixed layout.
- **System-aware theme.** Defaults to **System Default**, following your
  OS's light/dark preference live — switch your desktop theme while the
  app is open and it updates immediately, no restart needed. Dark and
  Light are also available directly (`Settings`, or `View → Toggle
  Dark/Light Theme`).
- **Merge Bins.** Combine a device's separate firmware images
  (bootloader, partition table, app, ...) into one flashable `.bin` via
  `esptool merge-bin`, entirely offline. Pre-merge validation catches
  missing files, invalid/duplicate addresses, and overlapping flash
  regions before esptool is even invoked. The merged file defaults to the
  same folder as `firmware.bin` (both the filename and location are
  configurable per-merge and as app-wide defaults in **Settings**), and
  you choose what happens to the source rows afterwards — add the merged
  bin, remove the source bins, de-select them, or leave Firmware Settings
  untouched — with a configurable default (Settings) of "add the merged
  bin and de-select the source bins."
- **Dynamic chip support.** The Chip Type list is no longer hardcoded — at
  startup the app asks the installed `esptool` itself which chips it
  supports, so new esptool releases add new chips automatically. If a
  project uses a chip your installed esptool no longer supports, you're
  warned clearly on load instead of finding out only when Upload fails.
- **Flash Encryption & Secure Boot provisioning.** A per-device
  **Security** tab generates or imports flash-encryption/secure-boot keys
  and burns them via `espsecure`/`espefuse` — the same official tools
  Espressif's own Flash Download Tool relies on, never reimplemented here.
  Burning eFuses is permanent on real hardware, so nothing runs until you
  both check an acknowledgement box and type an exact confirmation phrase
  on the Provision dialog; pre-flight validation catches missing key
  files, no chip selected, and (once you've read a device back) flashing
  plaintext firmware to a device that already shows encryption enabled.
- **Read Flash / eFuse / Chip Info.** A read-only inspection panel
  (`Tools → Read Flash / eFuse / Chip Info...`, or right-click a device),
  independent of the upload workflow, built on esptool's/espefuse's own
  chip-id/flash-id/get-security-info/read-flash/summary commands. Nothing
  it runs ever writes to flash or eFuse; read-back data can be saved to a
  file the same way Merge Bins' output is. Results land in two tabs — a
  plain-language **Summary** (chip model/revision, MAC address, flash
  manufacturer/size, secure boot/flash encryption state, ...) alongside
  the complete, unmodified **Log** — so you're not stuck reading raw
  esptool/espefuse text for the fields you actually need.
- Dockable/resizable panels, persistent window
  layout, user-customisable keyboard shortcuts (`Tools → Keyboard
  Shortcuts...`, with duplicate-assignment detection), and right-click
  context menus.
- **Assign Firmware Set to Devices...** (`Devices` menu). Stamp one
  imported firmware folder across all devices, or just the ones you've
  selected, in one step — every other feature (auto-detect, the
  pre-upload warning page, live progress) applies exactly as it does
  when importing firmware per-device.
- **Built-in Serial Monitor** (`Tools → Open Serial Monitor...`, or
  right-click a device → **Open Serial Monitor**). Open any number of
  ports at once, each in its own window, with baud-rate selection,
  auto-scroll, pause, search, save-to-file, and a send line — mirrors
  the Logs console's controls. Refuses to open a port that's mid-upload,
  and the upload validator refuses to start a flash on a port that
  already has a Serial Monitor connected, telling you to close it first.
- **Interface Lock, in two modes** (`Tools → Lock Interface`), both
  protected by the same key (stored as a SHA-256 hash, never in
  plaintext):
  - **Settings Lock** keeps the window fully usable —
    uploads, Serial Monitor, and viewing logs all keep working — but
    disables anything that reconfigures what gets flashed: ports,
    chip/flash settings, the firmware list (including Merge Bins), the
    Security tab, Batch Edit, Assign Firmware Set, Firmware Profiles, and
    deleting devices. Meant for handing a bench to an operator who should
    run a pre-configured job, not change it.
  - **Full Lock** — the original behaviour — freezes
    the *entire* window behind an opaque overlay; nothing is reachable
    until the key is re-entered. Refuses to lock while a Logs or Serial
    Monitor window is still open, and tells you which one(s) to close
    first.
  Batch Edit, Assign Firmware Set, and Firmware Profile application also
  refuse to touch a device that's actively uploading, regardless of lock
  mode — saving your project is never restricted.
- **Update checker** (`Tools → Check for Updates...`) that's aware of how
  *this* copy was obtained — an installed build is offered the next
  installer, a portable build is offered the next portable executable —
  and always leaves the actual install step to the OS-native installer.
- **Rotating log files** (application / flash / error / debug), so nothing
  is ever silently lost, and the app is built to *never crash* — every
  expected upload failure (bad cable, board not in bootloader mode, "No
  serial data received", etc.) is recognized and reported clearly in the
  device's status/Live Output/history instead of ever reaching a generic
  error dialog; anything truly unexpected is still caught, logged, and
  shown to the user in plain language.
- **Auto-Save.** Silently saves your project on a configurable interval
  (Disabled, or every 1–30 minutes) once it's been saved to disk at least
  once — a brand-new, never-saved project is never auto-saved on your
  behalf.
- **Dynamic MD5.** Firmware checksums are never trusted from the project
  file — they're recalculated from the actual `.bin` on disk every time
  a project loads, and flagged if a file changed since it was added.
- **QC Verification.** Mark any successfully-flashed device Pass/Fail
  after a physical bench check, stored with its history entry and
  included in CSV exports.
- **Device Traceability.** Every successful flash automatically captures
  the device's MAC address (via the same parsing esptool's own connect
  output already provides) and attaches it to that flash's history entry.
- **Sounds & Notifications.** Configurable sounds (or a plain system beep)
  for flash success/failure, batch completion, and device connect/
  disconnect, with per-event enable toggles (`Settings → Sounds`).
- **Device Groups & Tags.** Assign free-text tags (e.g. "Line A", "RFID
  Batch") to any device, then filter and sort the device list by tag —
  fully compatible with existing multi-selection and Assign Firmware Set.
- **Flash History search & filtering.** Narrow the History dock by device/
  MAC address, date range, result, or QC status, all combinable.

---

## Screenshots

The main window with a batch of devices configured, each with its own
port, chip type, and status:

![Main window with devices added](docs/images/devices-added.png)

Renaming a device and editing its per-device settings on the
**Device Settings** tab:

![Renaming a device on the Device Settings tab](docs/images/device-settings-rename.png)

Adding firmware `.bin` files to a device via **Add BIN...**:

![Add BIN file picker dialog](docs/images/add-bin-dialog.png)

The **Firmware** tab after bootloader/partition-table/app/firmware
images have been added, each with its flash address, size, and MD5:

![Firmware tab populated with bootloader, partition table, and app images](docs/images/firmware-tab-populated.png)

Saving the current bench configuration as a reusable `.efmproj` project
file via **File → Save Project As...**:

![Save Project As dialog](docs/images/save-project-dialog.png)

Per-device settings on the **Device Settings** tab — port, chip type,
baud rate, flash mode, and per-device flash options:

![Device Settings tab with a device selected](docs/images/device-settings-tab.png)

The **Security** tab, where flash encryption and secure boot are
configured per device before anything is ever burned:

![Security tab with Flash Encryption and Secure Boot options](docs/images/security-tab.png)

Right-click a device for quick actions, including **Read Flash / eFuse /
Chip Info...**:

![Device context menu](docs/images/device-context-menu.png)

The app always validates before it acts — for example, refusing to read
a device with no port selected instead of guessing:

![Read Flash dialog validation when no port is selected](docs/images/read-no-port-validation.png)

Batch-editing settings across multiple selected devices at once:

![Batch edit dialog](docs/images/batch-edit-dialog.png)

Assigning a saved firmware set to one or more devices in a single step:

![Assign firmware set dialog](docs/images/assign-firmware-set-dialog.png)

The **Flash History** dock, keeping a record of past uploads:

![Flash history dock](docs/images/flash-history-dock.png)

Picking a port for the built-in **Serial Monitor**:

![Serial monitor port picker dialog](docs/images/serial-monitor-port-dialog.png)

The **Lock Interface** submenu, which prevents accidental edits to
devices, firmware, or settings while uploads are in progress:

![Lock Interface submenu](docs/images/lock-interface-submenu.png)

App-wide preferences in **Settings**:

![Settings dialog](docs/images/settings-dialog.png)

Keyboard shortcuts reference (`Help → Keyboard Shortcuts`):

![Keyboard shortcuts dialog](docs/images/keyboard-shortcuts-dialog.png)

The **Help** menu, with quick access to the User Manual and About:

![Help menu open](docs/images/help-menu.png)

The **About** dialog:

![About dialog](docs/images/about-dialog.png)

See `docs/USER_MANUAL.md` for a complete walkthrough of every screen.

---

## ESP32 Multi Flash Manager vs. Espressif Flash Download Tool

Espressif's own [Flash Download Tool](https://www.espressif.com/en/support/download/other-tools)
("FDT") is the closest official equivalent to this project, so it's worth
being explicit about where the two overlap and where they differ, based
on FDT's own [published user guide](https://docs.espressif.com/projects/esp-test-tools/en/latest/esp32/production_stage/tools/flash_download_tool.html)
(v3.9.11, the latest documented release at the time of writing). Both
tools can flash real ESP32 hardware correctly; the difference is mostly
in workflow, platform reach, and how far past "flash one image" each one
goes.

| Capability | ESP32 Multi Flash Manager | Espressif Flash Download Tool |
| --- | --- | --- |
| **Operating systems** | Windows, macOS, Linux | Windows only (7/10) |
| **Source / license** | Open source (MIT); esptool/espefuse/espsecure remain separate GPLv2 dependencies | Closed-source freeware; no source available |
| **Underlying flashing implementation** | Drives the official `esptool` as a subprocess — no protocol logic reimplemented | Espressif's own standalone implementation, distinct from `esptool.py` |
| **Parallel/batch flashing** | Unlimited devices, each with its own thread and `esptool` subprocess | `FactoryMultiDownload` mode, documented up to 20 devices per session |
| **Per-device configuration** | Independent chip type, baud, flash mode/frequency/size, and custom arguments per device, editable anytime | One shared `SPI Flash Config` per session; `Factory` mode locks it by default to prevent accidental changes |
| **Firmware auto-detection** | Recognizes `bootloader.bin`, `partition-table.bin`, `firmware.bin`, etc. and assigns standard addresses automatically | None — each path and address is entered manually per slot |
| **Saved project / bench configuration** | `.efmproj` JSON project files (devices, firmware, settings, layout); reopening with missing files flags them for relinking | No project file format; `Factory` mode persists via the tool's own `bin/` folder layout and `.conf` files |
| **Combining firmware images** | Dedicated Merge Bins dialog with pre-merge validation (missing files, invalid/duplicate/overlapping addresses) before `esptool merge-bin` runs | `CombineBin` button concatenates selected files; no address-overlap validation reported to the user |
| **Read-back (chip/flash/eFuse)** | Chip Info, Flash ID, eFuse Summary, Security Info, and Read Flash Region, each with both a friendly **Summary** view and the complete raw **Log** | `chipInfoDump` tab covering Chip Info, Read Flash, and Read Efuse, added in tool version 3.9.8; output is raw text or a fixed-name file |
| **Flash Encryption / Secure Boot** | Per-device **Security** tab; keys generated/imported through `espsecure`; burning is blocked behind an explicit acknowledgement + typed confirmation phrase | Configured by hand-editing `security.conf` INI files per chip; supports Secure Boot v1/v2 and customer-supplied keys |
| **History / traceability** | Persistent flash history with CSV export (device, firmware, result, duration) | `CRC32 cal` button for factory-floor file/config verification; no persistent run history |
| **Reusable configuration** | Named Firmware Profiles, device cloning/templates, and batch editing across selected devices | None — each session's `Factory` mode config is the only reusable state |
| **Serial monitor** | Built-in, any number of concurrent port windows | Not included |
| **Access control** | Two lock modes (Settings Lock / Full Lock) behind a SHA-256-hashed key | `LockSettings` toggle in `Factory` mode — prevents accidental clicks, not an access-control mechanism |
| **Update checking** | Built in, aware of installed vs. portable builds | Manual — check Espressif's download page for new tool versions |
| **Theming** | System-aware light/dark, switchable live | Follows Windows' native look only |

### Which one should you choose?

- **Choose Espressif's Flash Download Tool** if you're on Windows only,
  need Espressif's own officially-supported binary for a factory line
  that's already standardized on it, or want `Factory` mode's
  locked-down, config-file-driven workflow for a non-technical operator
  who should never see a settings screen at all.
- **Choose ESP32 Multi Flash Manager** if you need macOS or Linux
  support, more than 20 devices at once, per-device (rather than
  per-session) settings, a saveable/reopenable project file, firmware
  auto-detection, flash/read history you can export, or you'd simply
  rather work with an open-source tool you can audit or extend yourself.

Both are safe choices for real production use — they lean on the same
underlying Espressif flashing protocol knowledge, just through different
implementations and with different target workflows. For a small bench
of Windows-only boards with a fixed, rarely-changing firmware set,
Espressif's tool is perfectly sufficient; for anything larger, more
cross-platform, or more automation-and-traceability-driven, this project
is the closer fit.

---

## Quick Start

```bash
# 1. Clone this repository and set up a virtual environment
git clone https://github.com/SomangshuDas/esp32_multi_flash_manager.git
cd esp32_multi_flash_manager
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies and run
pip install -r requirements.txt
python run.py
```

Runs identically on **Windows, macOS, and Linux** — there is no
platform-specific setup step. See `docs/BUILD_INSTRUCTIONS.md` for
packaging into a standalone executable on each OS, and
`docs/USER_MANUAL.md` for a full walkthrough of the interface.

Prefer not to run from source? Every
[tagged release](https://github.com/SomangshuDas/esp32_multi_flash_manager/releases)
ships an installer for each OS — built by the scripts in
[`packaging/`](packaging) — alongside the raw portable binary:
`Setup.exe` (Windows, via Inno Setup), a `.dmg` (macOS), and a `.AppImage`
(Linux). Each installer also registers the **`.efmproj` project file
extension** with the app, so double-clicking a project file opens it
directly instead of requiring `File → Open Project` first.

> **Installer testing status:**
> - ✅ **Windows 10** — tested
> - ⬜ **Linux** — not yet tested on real hardware/VM
> - ⬜ **macOS** — not yet tested on real hardware (no Apple hardware
>   available to the maintainer)
>
> If you install this on Linux or macOS and hit an issue, please
> [open an issue](https://github.com/SomangshuDas/esp32_multi_flash_manager/issues)
> or reach out — reports are very welcome.

An example project is included at `examples/example_project.efmproj`,
referencing dummy firmware in `examples/firmware/` — open it from
**File → Open Project** to explore the UI immediately. (The dummy `.bin`
files are placeholders sized like real ESP-IDF output, not real firmware —
do not flash them to a device you care about. The example device ports —
`COM5`, `COM6`, `COM7` — are just illustrative defaults; edit them to
match your actual OS's port names before flashing for real.)

---

## Architecture

```
app/
  ui/                 Qt widgets, dialogs, main window (View layer)
  models/              Plain-data models: DeviceConfig, FirmwareEntry,
                        ProjectModel, HistoryEntry (Model layer)
  controllers/         DeviceController, FlashController, ProjectController
                        mediate between models and views (Controller layer)
  flash_engine/        esptool command builder/subprocess wrapper + the
                        pre-upload validation engine + security_manager.py
                        (espsecure/espefuse command builder for flash
                        encryption / secure boot / eFuse reads)
  project_manager/     .efmproj save/load + recent-projects list
  device_manager/      Live serial port scanning (pyserial)
  firmware_manager/    Firmware folder auto-detection + named profiles
  workers/             QThread workers: one FlashWorker per device for true
                        parallel flashing, ProvisionWorker (eFuse burning)
                        and ReadWorker (Read Flash/eFuse/Chip Info), plus
                        PortWatcher for live port polling
  logging_setup/       Rotating log file configuration
  utilities/           Shared constants, helper functions, and the
                        cross-platform app-data / resource-path resolvers
resources/
  icons/                App icon (.ico + .svg) and toolbar SVG icon set
  themes/               Dark/light QSS stylesheets (also embedded in code)
examples/               Example project + example firmware folder
docs/                   User manual, developer docs, build instructions
packaging/               Installer scripts (Windows/.exe, macOS/.dmg,
                          Linux/.AppImage) + .efmproj file association
.github/workflows/      CI: cross-platform build + smoke test on every push,
                          plus installer builds on tagged releases
```

This follows a strict **MVC discipline**: models never import Qt or
controllers; controllers never import concrete widgets, only emit Qt
signals; views only talk to controllers, never to the flash engine or
project I/O directly. See `docs/DEVELOPER_DOCUMENTATION.md` for details on
extending the app (new chip support, new panels, a plugin system, etc.).

## Requirements

- **Windows, macOS, or Linux** — genuinely cross-platform, not a Windows
  app with incidental portability. Application data (settings, recent
  projects, profiles, logs) is written to each OS's own native app-data
  location; serial port discovery goes through `pyserial`, which already
  abstracts `COMx` vs `/dev/tty*` naming.
- Python 3.12+
- A working USB-to-serial driver for your ESP32 boards (CP210x / CH340 /
  FTDI, as applicable) — installed the same way you'd install any serial
  driver on your OS.
- The official `esptool` PyPI package (installed via `requirements.txt`) —
  this app never reimplements the ESP32 flashing protocol itself, it
  drives `esptool` as a subprocess for maximum protocol correctness and
  compatibility with future chips. Flash Encryption/Secure Boot
  provisioning and eFuse reads are built the same way, on top of the same
  package's `espsecure`/`espefuse` command-line tools.

## Continuous Integration

Every push and pull request to `main` is built and smoke-tested on all
three target platforms by
[`.github/workflows/build.yml`](.github/workflows/build.yml)
(`windows-latest`, `macos-latest`, `ubuntu-latest`), producing a
downloadable PyInstaller build artifact for each OS. Pushing a `v*.*.*`
tag additionally triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which
builds the installers under `packaging/` for all three OSes and attaches
them to the GitHub Release. See `docs/BUILD_INSTRUCTIONS.md` §5 for
details.

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for
the development setup, this codebase's conventions (strict MVC,
out-of-process `esptool`/`espefuse`/`espsecure`, irreversibility
safeguards, etc.), and how to submit a pull request. Please also read the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) before participating.

Found a security issue rather than a regular bug — especially anything
touching flash-encryption/secure-boot key handling or eFuse-burning
confirmations? Please follow [`SECURITY.md`](SECURITY.md) instead of
opening a public issue.

## License

MIT — see `LICENSE`. Note that `esptool` itself is GPLv2-licensed and is a
separate dependency, not redistributed by this project.

## Author

Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
