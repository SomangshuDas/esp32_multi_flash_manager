# ESP32 Multi Flash Manager

A production-grade, cross-platform desktop application for flashing
firmware onto an **unlimited number of ESP32 devices in parallel**, built
on top of the official [`esptool`](https://github.com/espressif/esptool)
backend for reliability.

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
  boolean flags (erase / verify / reset / compression / stub loader), plus
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
- **Dark and light themes**, dockable/resizable panels, persistent window
  layout, keyboard shortcuts, and right-click context menus.
- **Rotating log files** (application / flash / error / debug), so nothing
  is ever silently lost, and the app is built to *never crash* — every
  exception is caught, logged, and shown to the user in plain language.

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
                        pre-upload validation engine
  project_manager/     .efmproj save/load + recent-projects list
  device_manager/      Live serial port scanning (pyserial)
  firmware_manager/    Firmware folder auto-detection + named profiles
  workers/             QThread workers: one FlashWorker per device for true
                        parallel flashing, plus PortWatcher for live port
                        polling
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
  compatibility with future chips.

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

## License

MIT — see `LICENSE`. Note that `esptool` itself is GPLv2-licensed and is a
separate dependency, not redistributed by this project.

## Author

Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
