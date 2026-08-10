# User Manual — ESP32 Multi Flash Manager

This guide walks through day-to-day use of the application on a
manufacturing or lab bench.

## 1. Launching the app

```bash
pip install -r requirements.txt
python run.py
```

Or use the packaged standalone build if you've made one (see
`BUILD_INSTRUCTIONS.md`) — `ESP32MultiFlashManager.exe` on Windows,
`ESP32MultiFlashManager.app` on macOS, or the `ESP32MultiFlashManager`
binary on Linux.

If you installed the app via one of the installers under `packaging/`
(`Setup.exe` on Windows, the `.dmg` on macOS, or the `.AppImage` on
Linux — see §10 for more) you can also just **double-click any `.efmproj`
file**: the app launches directly with that project already loaded, no
manual `File → Open Project` step needed.

## 2. The main window

- **Top bar (Dashboard):** live counts of Total, Connected, Disconnected,
  Ready, Uploading, Failed, and Completed devices.
- **Left panel (Device List):** one row per configured device, with its
  status badge, progress bar, elapsed time, ETA, and transfer speed. Every
  column — including Name — can be resized by dragging its header edge to
  fit your workflow. Right-click a row (or multi-select with Ctrl/
  Shift-click) for a context menu with Upload Selected / Cancel Selected /
  Duplicate / Remove.
- **Right panel:** two tabs for whichever device is selected —
  **Firmware** (its list of `.bin` files) and **Device Settings** (port,
  chip, baud, flash mode/frequency/size, and the flashing option
  checkboxes).
- **Bottom dock (Flash History):** every past flash attempt, with an
  **Export CSV** button.
- **Status bar:** overall progress for the current batch and a running
  status message.

## 3. Adding and configuring a device

1. Click **+ Add Device** (or `Ctrl+D`).
2. Select it in the list, then open the **Device Settings** tab and fill
   in: Friendly Name, Port (pick from the live dropdown or type one),
   Chip Type, Upload Speed, Flash Mode/Frequency/Size, and the flashing
   toggles (Erase / Verify / Reset / Compression / Stub Loader). You can
   also add raw extra `esptool` arguments in **Custom Flash Arguments**.
3. Switch to the **Firmware** tab to add `.bin` files (see next section).

To quickly configure many similar boards, configure one device fully, then
select it and click **Duplicate** — the clone keeps every setting except
its port (which is left blank so you don't accidentally double-flash
the same port).

## 4. Adding firmware

On the **Firmware** tab for a device, you have four ways to add files:

- **Add BIN...** — pick one or more `.bin` files manually; you set the
  address afterwards.
- **Auto-Detect Folder...** — point at a build output directory (e.g. your
  ESP-IDF `build/` folder). Recognized filenames
  (`bootloader.bin`, `partition-table.bin`, `partitions.bin`,
  `ota_data_initial.bin`, `boot_app0.bin`, `firmware.bin`, `app.bin`) get
  their standard address automatically; anything else is added with a
  placeholder address (`0x0`) for you to fill in.
- **Drag & drop** — drag `.bin` files, or an entire firmware folder,
  straight onto the Firmware panel.
- Reorder with **Move Up** / **Move Down**, remove a row with **Remove**,
  or clone a row with **Duplicate**.

Each row has an **On** checkbox — unchecked rows are skipped when
flashing (useful for temporarily excluding a file without deleting it).

Addresses are edited in place in the table; entering something that isn't
valid hex (e.g. `0x10000`) is rejected with a warning.

## 5. Uploading

- **Upload Selected** (`F5`, or the toolbar button) flashes only the
  devices currently selected in the list.
- **Upload All** (`Ctrl+F5`) flashes every configured device.
- Right-click a multi-selection for **Upload Selected (N)** from the
  context menu.

Before anything is sent to hardware, the app runs a **validation pass**
and shows a report if it finds problems:

- **Errors** (block the upload): duplicate ports, no port
  selected, missing firmware files, invalid or duplicate flash addresses,
  invalid chip/flash-mode selection, no enabled firmware.
- **Warnings** (you may proceed anyway): no firmware assigned to the
  conventional bootloader (`0x1000`) or partition-table (`0x8000`)
  addresses — this is expected if you're flashing a single merged image.

Once underway, each device flashes independently and in parallel: its own
status badge walks through *Waiting → Preparing → Connecting → Erasing →
Uploading → Verifying → Completed* (or *Failed*/*Cancelled*), its own
progress bar fills, and its own elapsed/ETA/speed columns update live.

## 6. Watching progress / live output

Click **View Log** on any device row to open its **Live Output** window —
the raw `esptool` console output, streamed in real time. Inside that
window you can:

- **Pause / Resume** — freeze the view without losing incoming lines
  (they're queued and flushed when you resume).
- **Search** — find text in the log (press Enter to jump to the next
  match; wraps around).
- **Copy** — copy the entire visible log to the clipboard.
- **Save Log...** — write it to a `.log`/`.txt` file.
- **Clear** — empty the console.
- **Auto-scroll** — checkbox to keep the view pinned to the latest line.

## 7. Cancelling and retrying

- **Cancel Selected** / **Cancel All** stop in-progress flashes for the
  chosen devices (the `esptool` subprocess is terminated cleanly).
- **Retry Failed** re-uploads every device currently in the *Failed*
  state.
- **Retry Selected** re-uploads whatever is currently selected,
  regardless of its last status.

## 8. Batch editing

**Devices → Batch Edit...** (`Ctrl+B`) lets you change one setting (e.g.
baud rate, flash mode, or any of the boolean flags) across **All
devices** or just the **currently selected** ones, in one action — handy
when you realize halfway through setup that every board should use
115200 baud instead of the default.

## 9. Firmware Profiles

**Devices → Firmware Profiles...** with a device selected lets you:

- **Apply** a previously saved profile to that device (overwrites its
  firmware list and flash settings).
- **Save As New Profile...** to capture the selected device's current
  firmware list + settings under a name like "ESP32 RFID Reader", so it
  can be reused on other devices or in future projects.
- **Delete** a profile you no longer need.

## 10. Projects

- **File → New Project** (`Ctrl+N`) starts fresh (asks first if you have
  unsaved changes).
- **File → Open Project...** (`Ctrl+O`) loads a `.efmproj` file.
- **File → Save Project** (`Ctrl+S`) / **Save Project As...**
  (`Ctrl+Shift+S`).
- **File → Recent Projects** lists your last 10 opened/saved projects.

If a project references firmware files that no longer exist at their
saved path (e.g. you moved the build folder), the project still loads —
you'll get a warning dialog listing what's missing, and the affected rows
are marked **Missing!** in red on the Firmware tab. Use **Add BIN...** to
relink them.

**Opening a project by double-clicking it.** If the app was installed via
one of the OS installers built from `packaging/` (rather than run from
source or a raw portable binary), `.efmproj` files are registered with the
app:

- **Windows:** double-click a `.efmproj` file in Explorer, or right-click →
  Open With → ESP32 Multi Flash Manager.
- **macOS:** double-click it in Finder, or drag it onto the app's Dock icon.
- **Linux:** works once the AppImage is integrated with your desktop (e.g.
  via `appimaged`/AppImageLauncher) — double-click from your file manager.

Either way this launches the app with that project already open — the
project on the command line is treated exactly like `File → Open Project`,
including the same missing-firmware warning behavior above.

## 11. Searching devices

Type into the search box above the device list to filter by name,
port, chip type, or current status — the list narrows as you type.

## 12. Flash history

The **Flash History** dock (bottom of the window, toggle via **View**
menu) accumulates every attempt across the session: date, time, device
name, port, firmware summary, duration, and result. Click **Export
CSV...** to save it for QA/traceability records, or **Clear History** to
reset it.

## 13. Settings

**Tools → Settings...** lets you set the default theme (dark/light),
default baud rate, and default flash mode for new devices, and gives you
a one-click **Open Logs Folder** button if you need to send logs to
support.

## 14. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New Project |
| `Ctrl+O` | Open Project |
| `Ctrl+S` | Save Project |
| `Ctrl+Shift+S` | Save Project As |
| `Ctrl+D` | Add Device |
| `Ctrl+B` | Batch Edit |
| `F5` | Upload Selected |
| `Ctrl+F5` | Upload All |
| `Esc` | Cancel All |
| `Ctrl+T` | Toggle Dark/Light Theme |
| `Ctrl+Q` | Exit |

## 15. Troubleshooting

- **"esptool could not be launched"** — make sure `pip install -r
  requirements.txt` succeeded and that `python -m esptool version` works
  from the same environment you're running this app in.
- **A device won't connect** — check the port is correct (unplug/
  replug and watch the status bar toast; the dashboard's Disconnected
  tile also flags it), and that no other program (Arduino IDE Serial
  Monitor, PlatformIO, etc.) is holding the port open.
- **Duplicate port error at upload time** — two devices in your
  selection share the same port; only one can use it at once. Fix one
  of them in the Device Settings tab.
- Logs are in the app's per-OS data folder — `Tools → Settings → Open
  Logs Folder` opens it directly on any platform. If you need the path
  manually: `%APPDATA%\ESP32MultiFlashManager\logs\` on Windows,
  `~/Library/Application Support/ESP32MultiFlashManager/logs/` on macOS,
  or `~/.local/share/ESP32MultiFlashManager/logs/` on Linux.

---

Author: Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
