# Build Instructions — ESP32 Multi Flash Manager

ESP32 Multi Flash Manager is a plain Python + PySide6 application with no
platform-specific code paths that matter at the source level — it runs
identically on **Windows, macOS, and Linux** via `python run.py`. This
document covers running it from source, verifying your environment, and
packaging it into a standalone executable on each of the three platforms.

The exact commands below are also run automatically on every push in
[`.github/workflows/build.yml`](../.github/workflows/build.yml), which
builds on `windows-latest`, `macos-latest`, and `ubuntu-latest` — that
workflow is the source of truth if this document ever drifts from it.

---

## 1. Run from source (recommended for development)

Requires Python 3.12+ on any of Windows, macOS, or Linux.

```bash
# From the project root
python -m venv .venv

# Windows (Command Prompt / PowerShell)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

To see debug-level console logging in addition to the rotating log files,
run:

```bash
python run.py --debug
```

## 2. Verify the environment before building

```bash
python -m esptool version
```

This should print the installed `esptool` version. If it fails, fix your
Python environment before proceeding — the app calls `esptool` exactly
this way (`python -m esptool ...`) under the hood, on every platform.

## 3. Package as a standalone executable (PyInstaller)

```bash
pip install pyinstaller
```

The bundled icon assets are already in the right formats for each
platform's packager:

- `resources/icons/app_icon.ico` — multi-resolution (16/32/48/64/128/256)
  Windows icon, used directly.
- `resources/icons/app_icon.svg` — master vector source, used at runtime
  for the in-app window icon on every OS, and as the source for the macOS
  `.icns` conversion below.

### Windows

```powershell
pyinstaller --noconfirm --windowed --onefile ^
  --name ESP32MultiFlashManager ^
  --icon resources\icons\app_icon.ico ^
  --add-data "resources;resources" ^
  --collect-all esptool ^
  run.py
```

Output: `dist\ESP32MultiFlashManager.exe`

### macOS

PyInstaller wants a `.icns` file for the app bundle icon rather than the
`.ico`/`.svg`. Generate one from the bundled SVG once per release:

```bash
mkdir icon.iconset
for size in 16 32 128 256 512; do
  sips -z $size $size -s format png resources/icons/app_icon.svg \
    --out "icon.iconset/icon_${size}x${size}.png"
  double=$((size * 2))
  sips -z $double $double -s format png resources/icons/app_icon.svg \
    --out "icon.iconset/icon_${size}x${size}@2x.png"
done
iconutil -c icns icon.iconset -o resources/icons/app_icon.icns
rm -rf icon.iconset
```

(If `sips` can't rasterize SVG directly on your macOS version, export a
512×512 PNG from the SVG with any tool first and feed that to `sips`
instead.)

```bash
pyinstaller --noconfirm --windowed --onefile \
  --name ESP32MultiFlashManager \
  --icon resources/icons/app_icon.icns \
  --add-data "resources:resources" \
  --collect-all esptool \
  run.py
```

Output: `dist/ESP32MultiFlashManager.app`

Note the `:` separator for `--add-data` on macOS/Linux, versus `;` on
Windows.

### Linux

```bash
pyinstaller --noconfirm --onefile \
  --name ESP32MultiFlashManager \
  --add-data "resources:resources" \
  --collect-all esptool \
  run.py
```

Output: `dist/ESP32MultiFlashManager` (a self-contained ELF binary).

For a desktop-integrated launcher, create a `.desktop` entry pointing at
the built binary and `resources/icons/app_icon.svg` (most Linux desktop
environments accept SVG icons directly):

```ini
[Desktop Entry]
Type=Application
Name=ESP32 Multi Flash Manager
Exec=/path/to/dist/ESP32MultiFlashManager
Icon=/path/to/resources/icons/app_icon.svg
Categories=Development;Electronics;
```

Also make sure your user account can access serial devices:

```bash
sudo usermod -a -G dialout $USER
# log out and back in for the group change to take effect
```

### Notes common to all three platforms

- `--windowed` (Windows/macOS) suppresses the console window — the app has
  its own log files and error dialogs, so a console isn't needed for
  normal use. Linux `--onefile` builds don't take `--windowed`; the app
  still runs GUI-only.
- `--collect-all esptool` is important on every platform: esptool ships
  data files (e.g. stub loader binaries) that PyInstaller's default
  analysis can miss; this flag forces them to be bundled.
- Because `esptool` is launched via `sys.executable -m esptool` (see
  `app/flash_engine/esptool_wrapper.py`), a PyInstaller `--onefile` build
  works correctly on every OS: `sys.executable` inside a frozen app points
  at the bundled executable itself, and esptool's package is importable
  from inside it since it was collected into the bundle.
- Icons and themes are resolved through `resource_path()` in
  `app/utilities/helpers.py`, which checks for PyInstaller's `sys._MEIPASS`
  first — this is what keeps the window icon working identically whether
  you run from source or from a frozen build, on any OS.

## 4. Building an installer (optional)

- **Windows** — wrap the PyInstaller `.exe` with
  [Inno Setup](https://jrsoftware.org/isinfo.php) or
  [NSIS](https://nsis.sourceforge.io/) for a proper `Setup.exe` with Start
  Menu shortcuts and an uninstaller:

  ```ini
  [Setup]
  AppName=ESP32 Multi Flash Manager
  AppVersion=1.0.0
  DefaultDirName={autopf}\ESP32MultiFlashManager
  DefaultGroupName=ESP32 Multi Flash Manager
  OutputBaseFilename=ESP32MultiFlashManagerSetup
  Compression=lzma2
  SolidCompression=yes

  [Files]
  Source: "dist\ESP32MultiFlashManager.exe"; DestDir: "{app}"; Flags: ignoreversion

  [Icons]
  Name: "{group}\ESP32 Multi Flash Manager"; Filename: "{app}\ESP32MultiFlashManager.exe"
  ```

- **macOS** — distribute the `.app` bundle directly, or wrap it in a `.dmg`
  with `hdiutil create` for a drag-to-Applications installer experience.
- **Linux** — distribute the single binary plus the `.desktop` file above,
  or package as an AppImage if you want a fully self-contained,
  distro-agnostic artifact.

## 5. Continuous Integration

[`.github/workflows/build.yml`](../.github/workflows/build.yml) runs on
every push and pull request to `main` (and can be triggered manually via
`workflow_dispatch`). For each of `windows-latest`, `macos-latest`, and
`ubuntu-latest` it:

1. Installs Python 3.12 and the project's dependencies plus PyInstaller.
2. Byte-compiles the whole `app` package (`python -m compileall app`) so a
   syntax error fails fast.
3. Imports `app.main` headlessly (`QT_QPA_PLATFORM=offscreen`) as a smoke
   test that the app's import graph and Qt wiring are sound.
4. Runs the exact PyInstaller command documented above for that OS.
5. Uploads the resulting executable/bundle as a build artifact
   (`ESP32MultiFlashManager-windows` / `-macos` / `-linux`), downloadable
   from the workflow run's **Summary** page.

This means every commit gets an actual cross-platform build verification,
not just a "should work on Linux/macOS" assumption — a build that fails on
Windows or macOS fails CI, the same as a failing build on Linux would.

## 6. Verifying a build manually

1. Launch the built executable/bundle on a clean machine (or VM) that has
   never had the Python source environment on it.
2. Confirm `File → New Project`, `Devices → Add Device`, and
   `Firmware → Auto-Detect Folder...` (pointed at `examples/firmware`) all
   work.
3. Plug in a real ESP32 board, set its port, and try
   `Flash → Upload Selected` against a known-good firmware image to
   confirm the bundled `esptool` launches correctly from inside the frozen
   executable.
4. Confirm the app's log directory is being written to — see
   `docs/DEVELOPER_DOCUMENTATION.md` → **Logging** for the exact path on
   your OS.

## 7. Directory layout expected at runtime

The app does not require write access to its own install directory — all
persistent data (settings, recent projects, firmware profiles, logs) is
written under the per-OS application-data directory (see
`app/utilities/helpers.py::get_app_data_dir`), so it's safe to install
into `Program Files`, `/Applications`, or `/opt` on locked-down
manufacturing PCs on any platform.

---

Author: Somangshu Das — [github.com/SomangshuDas](https://github.com/SomangshuDas)
