# User Manual — ESP32 Multi Flash Manager

This guide walks through day-to-day use of the application on a
manufacturing or lab bench. It's also one click away inside the app
itself via **Help → User Manual**, which always opens this
same file on GitHub so it's never out of sync with the version you're
running.

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
  Open Serial Monitor (single selection only) / Duplicate / Remove.
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
   toggles (Erase / Reset / Compression / Stub Loader). You can
   also add raw extra `esptool` arguments in **Custom Flash Arguments**.
   Flash verification now happens automatically after every write (esptool
   v5+), so there is no longer a separate Verify toggle.
   The **Chip Type** list is populated at startup from your installed
   `esptool` itself, so it always matches what your copy of esptool can
   actually flash (see §18 for what happens if a project uses a chip your
   esptool no longer supports).
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

### Merging bins

Click **Merge Bins...** on the Firmware panel to combine a device's
separate firmware images (bootloader, partition table, app, ...) into one
flashable `.bin`, using `esptool`'s own `merge-bin` command:

1. Check the box on each row you want included in the merge (defaults to
   whatever is currently **On**).
2. Pick a **Target Chip** — this must be a specific chip (not "Auto"),
   since esptool needs to know the target chip to lay the merged image
   out correctly.
3. The **Output File** defaults to the same folder as `firmware.bin`
   (falling back to the first file's folder if there's no file literally
   named `firmware.bin`), using the default filename configured in
   **Settings**. Change the filename and/or location with **Browse...**
   or by editing the field directly.
4. Click **Validate** to check for problems before merging — missing
   files, invalid or duplicate addresses, and overlapping flash regions
   are all caught here, with errors (blocking) shown separately from
   warnings (which you can proceed past after confirming).
5. Choose what happens to the source rows **After Merging**:
   - *Add merged bin, de-select source bins* — the merged file is added
     as a new row and the original rows are unchecked (**On**) but kept,
     so you can still see what went into the merge.
   - *Add merged bin, remove source bins* — the merged file is added and
     the original rows are deleted from the device.
   - *Add merged bin only* — the merged file is added; the source rows
     are left exactly as they were.
   - *Do nothing to Firmware Settings* — the file is written to disk but
     nothing changes in the Firmware panel.
   The option shown by default here comes from **Settings → Default
   Post-Merge Action**.
6. Click **Merge**. Merging runs entirely offline (no device connection
   needed) and normally finishes in well under a second.

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
  overlapping flash addresses (see below), invalid chip/flash-mode
  selection, no enabled firmware.
- **Warnings** (you may proceed anyway): no firmware assigned to the
  conventional bootloader (`0x1000`) or partition-table (`0x8000`)
  addresses — this is expected if you're flashing a single merged image.

**Overlapping addresses.** Two firmware entries can use two different,
non-duplicate addresses and still collide once file size is taken into
account. The most common case: a full merged image (one `.bin` that
already contains its own bootloader, partition table, and app — the kind
esptool writes when you pass a single file at `0x0`) flashed *alongside*
a separate `bootloader.bin` at `0x1000` and/or `partition-table.bin` at
`0x8000`. The merged image is almost always well past 4 KB, so it
overwrites those addresses before esptool even gets there. The validator
now catches this before anything reaches hardware — if you see it,
either disable the separate bootloader/partition-table rows and flash
only the merged image at `0x0`, or don't enable the `0x0` merged image
alongside them.

Once underway, each device flashes independently and in parallel: its own
status badge walks through *Waiting → Preparing → Connecting → Erasing →
Uploading → Verifying → Completed* (or *Failed*/*Cancelled*), its own
progress bar fills, and its own elapsed/ETA/speed columns update live.

If a device disconnects mid-upload and never responds again (the flash
never completes, errors, or times out), the app now abandons that
device's flash automatically after about 45 seconds of silence and marks
it *Failed* with a "device appears to have disconnected" message — it no
longer sits stuck on *Uploading* until you restart the app, and its
Serial Monitor is no longer permanently blocked as "currently uploading."

While a device's status is anywhere in *Preparing → Verifying* (i.e. an
upload is actually running against it), that device's Device Settings
panel is locked (read-only, with a "locked — flashing in progress" note
in its title) and it can't be removed from the project — this prevents
changing its port/chip/flash options or deleting it out from under the
in-progress flash. This does **not** apply to that device's Live Output
window or an open Serial Monitor on its port; both stay fully usable
while the upload runs.

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
230400 baud instead of the default 115200.

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

**Tools → Settings...** lets you set:
- **Theme** — **System Default** (follows your OS's light/dark setting,
  live — no restart needed if you switch your OS theme while the app is
  open), or explicit **Dark**/**Light**.
- Default baud rate and default flash mode for new devices.
- **Bin Merge defaults** — default merged filename, default output
  location (leave blank to always use the same folder as `firmware.bin`),
  and the default **Post-Merge Action** pre-selected in the Merge Bins
  dialog (see §4 "Merging bins").

A one-click **Open Logs Folder** button is also here if you need to send
logs to support.

## 14. Serial Monitor

**Tools → Open Serial Monitor...** (or right-click a device row →
**Open Serial Monitor**) opens a live, two-way view of a board's serial
output — the same job as the Arduino IDE's or PlatformIO's serial
monitor, built in so you don't need a second tool. Pick the port (and,
from the device row, its saved baud rate is pre-filled) and click
**Connect**; you can open as many of these windows as you have ports
for, each independent, with its own baud-rate selector, auto-scroll,
Pause/Resume, search, Copy, Save Log..., Clear, and a send line (with a
line-ending choice) for talking back to the device.

Two safeguards keep it from colliding with flashing:
- Opening a monitor on a port that's currently mid-upload is refused —
  wait for the upload to finish first.
- Starting an upload on a port that already has a *connected* Serial
  Monitor open is refused by the pre-upload validation page, which
  tells you exactly which port's monitor to close first.

## 15. Assign Firmware Set to Devices

**Devices → Assign Firmware Set to Devices...** is built for the "one
firmware set, many identical devices" workflow common on a
manufacturing bench. It imports one firmware folder with the same
auto-detect used on the Firmware tab, then asks explicitly whether to
apply the resulting `.bin` + address list to **All Devices** or just
your currently **Selected Devices** (that option only appears if you
have a selection) — no more re-importing the same folder once per
board. Every other feature works exactly as it does when importing
firmware per-device: auto-detect, the pre-upload warning page, live
per-device progress, history, everything.

## 16. Locking the interface

There are two lock modes, both under **Tools → Lock Interface**, and both
protected by the same unlock key.

**Settings Lock** keeps the app fully usable — uploads,
Serial Monitor, and viewing logs all keep working — but disables anything
that reconfigures what gets flashed: ports, chip/flash settings, the
firmware list (including Merge Bins), **Batch Edit**, **Assign Firmware
Set to Devices**, **Firmware Profiles**, and deleting devices. This is
meant for handing a bench to an operator who should run a job that's
already configured for them, without being able to change it. Turning it
off asks for the unlock key.

**Full Lock** freezes the entire window — menus,
toolbars, device list, firmware/settings panels, everything — behind a
full-screen "Interface Locked" prompt, so you can walk away from a
running batch on a shared bench PC without someone bumping a setting or
cancelling an upload. If a Logs or Serial Monitor window is still open
when you try to lock, locking is refused and you're told which window(s)
to close first — those are separate windows the lock can't reach, so
leaving one open would leave a hole in it.

The first time you use either lock mode, you'll be asked to set an
**unlock key** (**Tools → Set Interface Lock Key...**, entered twice to
confirm). The key itself is never stored — only its hash — so locking
later just asks for that same key back. Closing the window (including
the OS close button) is blocked while Full Lock is active; unlock first,
then exit normally if you need to. The two modes are independent and can
be combined (e.g. Settings Lock on, then Full Lock on top before walking
away).

Separately, whether or not either lock is active: **Batch Edit**,
**Assign Firmware Set to Devices**, and **Firmware Profiles** always
refuse to modify a device that's currently uploading — that device is
skipped with a warning rather than having its settings rewritten out from
under a running upload. Saving your project is never restricted.

## 17. Keyboard shortcuts

**Tools → Keyboard Shortcuts...** lets you remap any action below to a
key sequence of your choice; the app warns you (and blocks Save) if two
actions end up sharing the same shortcut. **Reset to Defaults**
restores everything shown here. Any action not listed here (e.g. Cancel
Selected, Retry Failed) has no default shortcut and isn't customisable.

| Default Shortcut | Action |
|---|---|
| `Ctrl+N` | New Project |
| `Ctrl+O` | Open Project |
| `Ctrl+S` | Save Project |
| `Ctrl+Shift+S` | Save Project As |
| `Ctrl+D` | Add Device |
| `Ctrl+B` | Batch Edit |
| `Ctrl+Shift+A` | Assign Firmware Set to Devices |
| `F5` | Upload Selected |
| `Ctrl+F5` | Upload All |
| `Esc` | Cancel All |
| `Ctrl+T` | Toggle Dark/Light Theme |
| `Ctrl+M` | Open Serial Monitor |
| `Ctrl+Shift+L` | Full Lock |
| `Ctrl+Shift+F` | Settings Lock |
| `Ctrl+Q` | Exit |

## 18. Troubleshooting

- **"esptool could not be launched"** — make sure `pip install -r
  requirements.txt` succeeded and that `python -m esptool version` works
  from the same environment you're running this app in.
- **A device won't connect** — check the port is correct (unplug/
  replug and watch the status bar toast; the dashboard's Disconnected
  tile also flags it), and that no other program (Arduino IDE Serial
  Monitor, PlatformIO, this app's own Serial Monitor, etc.) is holding
  the port open.
- **"No serial data received" / upload fails immediately** — this means
  esptool couldn't get a response from the board at all: check the cable
  (data cable, not charge-only), that the board is in bootloader mode if
  it requires manually holding BOOT, and that the correct port is
  selected. This is reported directly in the device's status, Live
  Output, and history — not as an application error.
- **"Close the Serial Monitor before uploading"** — this app's own
  built-in Serial Monitor (§14) is connected to the same port you're
  trying to flash; esptool can't share a port with anything else.
  Disconnect or close that Serial Monitor window, then upload again.
- **"Unsupported/invalid chip selection" or a startup warning about an
  unsupported chip** — the app asks your installed `esptool` at startup
  which chips it supports (see §4); if a project uses a chip your
  installed esptool doesn't report support for, you're warned on load and
  the validator blocks uploading to that device. Update `esptool`
  (`pip install --upgrade esptool`) or correct the chip type in Device
  Settings.
- **Duplicate port error at upload time** — two devices in your
  selection share the same port; only one can use it at once. Fix one
  of them in the Device Settings tab.
- **"overlaps" error in the validation report** — a firmware entry's
  address plus its file size runs into the next entry's address. This
  happens most often when a full merged image (already containing its
  own bootloader/partition table) is enabled at `0x0` at the same time
  as separate `bootloader.bin`/`partition-table.bin` rows — disable one
  or the other, don't flash both.
- **A device's Settings panel is locked / grey / won't accept edits** —
  that device is currently flashing (status somewhere between
  *Preparing* and *Verifying*). Wait for it to finish or cancel it first;
  the panel unlocks automatically the moment it's no longer busy.
- **Can't remove a device** — same cause as above: a device that's
  mid-flash can't be removed while its upload is in progress.
- **A device is stuck on "Uploading" and its Serial Monitor keeps
  saying "currently uploading firmware"** — if the device disconnected
  mid-flash, the app auto-fails that device after about 45 seconds of no
  response instead of hanging indefinitely; give it that long before
  assuming something's wrong. If it's still stuck well past that, it's
  worth reporting as a bug rather than restarting the app.
- **Forgot the interface lock key** — there is no recovery/reset path by
  design (that's the point of a lock). You'll need to close the app from
  the OS (e.g. Task Manager / `kill`, losing unsaved project changes) and
  relaunch it.
- Logs are in the app's per-OS data folder — `Tools → Settings → Open
  Logs Folder` opens it directly on any platform. If you need the path
  manually: `%APPDATA%\ESP32MultiFlashManager\logs\` on Windows,
  `~/Library/Application Support/ESP32MultiFlashManager/logs/` on macOS,
  or `~/.local/share/ESP32MultiFlashManager/logs/` on Linux.

---

Author: Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
