<!-- APP_VERSION: 0.14.0 -->
# Changelog

All notable changes to ESP32 Multi Flash Manager are documented here,
newest first. This file was introduced in 0.13.0; for the history of
earlier releases (v0.1.0 through v0.12.0), see the repository's
[GitHub Releases](https://github.com/SomangshuDas/esp32_multi_flash_manager/releases)
page or `git log`/`git tag`.

The `<!-- APP_VERSION: X.Y.Z -->` comment at the top of this file (and of
README.md) is machine-checked: `.github/workflows/version_check.yml`
fails a tagged-release build if either marker's version doesn't match
`APP_VERSION` in `app/utilities/constants.py`. Bump both when you bump
that constant.

## [0.14.0] - 2026-09-09

### Added
- **Batch/multi-device provisioning**: `Tools → Provision Devices
  (Batch)...` burns eFuses (Flash Encryption / Secure Boot) across every
  selected device in one pass instead of requiring the single-device
  Provision dialog to be opened and confirmed once per device. Runs
  pre-flight validation on every candidate, skips (with a reason) any
  device that isn't configured for provisioning or fails validation, and
  gates the whole batch behind one explicit irreversible-burn
  confirmation. New `ProvisionController` applies the same
  parallel-cap/queue design as parallel flashing.
- **Max Parallel Provisions** setting (Settings → General → Provisioning,
  default 8, adjustable 1–32, matching **Max Parallel Flashes** so a
  bench sized for parallel flashing doesn't unexpectedly bottleneck on
  batch provisioning throughput): caps how many devices
  `ProvisionController` burns eFuses on concurrently; devices beyond the
  cap queue and launch automatically as running ones finish. The
  irreversible-burn confirmation gate — not the concurrency cap — is
  what actually limits blast radius for eFuse burning.
- **Provision Stall Timeout** setting (Settings → General → Provisioning,
  default 60s, adjustable 10–600s): now user-configurable, mirroring the
  existing Flash Stall Timeout setting. Previously this value was a
  hardcoded constant with no way to tune it from the UI.
- **CSV bulk device import** (`Devices → Import Devices from CSV...`,
  `app/project_manager/csv_import.py`): populate the device list in one
  step from a spreadsheet. Only a `name` column is required;
  `com_port`, `chip_type`, `baud_rate`, and semicolon-separated `tags`
  are recognized if present. A row with a missing name or invalid
  baud rate is skipped and reported after import, rather than aborting
  the whole file.
- **Default Device Profile** setting (Settings → General): optionally
  applies a saved Firmware Profile's chip/flash settings and firmware
  list to every newly-added device (via "Add Device" or CSV import),
  instead of the app's built-in defaults.
- **Diagnostics bundle export** (`Help → Export Diagnostics Bundle...`,
  also in Settings → Diagnostics, `app/utilities/diagnostics.py`): saves
  a single `.zip` containing all current log files plus app/OS/Python/
  `esptool` version information, for attaching to a bug report.
- **Optional structured JSON logging** (Settings → Diagnostics → "Enable
  structured JSON logging"), off by default: mirrors every log record as
  one JSON object per line to a new `events.jsonl` file, alongside
  (never instead of) the four existing rotating text logs, for anyone
  piping logs into a log-aggregation tool.
- **Opt-in, local-only anonymous usage/crash telemetry** (Settings →
  Privacy, `app/utilities/telemetry.py`), off by default. Recorded
  events use a fixed, reviewed event set and a random per-install
  client ID; never include device serials, COM port names, firmware
  file names/paths, or project names. This build stores events locally
  only — nothing is transmitted over the network regardless of the
  setting. See `docs/PRIVACY.md` for the full disclosure and
  `ROADMAP.md` for the (deliberately deferred) collection-backend work.
- **New Settings tabs**: **Advanced** (Port Scan Interval, Live Log Max
  Lines, Project Lock Stale After — previously hardcoded constants, now
  user-configurable with the same defaults as before), **Diagnostics**,
  and **Privacy** (see above).
- **`.emfm` project-file input-validation hardening**
  (`app/project_manager/project_io.py`): a file-size cap (25 MiB),
  checked before parsing, plus post-parse caps on device count (2000)
  and firmware entries per device (200), so a corrupted or hostile
  project file fails fast with a clear message instead of risking a UI
  hang or excessive memory use. See new `docs/THREAT_MODEL.md` for the
  full writeup, including why firmware file-path traversal is
  deliberately *not* restricted.
- `docs/THREAT_MODEL.md`, `docs/FAQ.md`, and `ROADMAP.md` (design
  sketches for dry-run validation, a Batch Edit/Assign Firmware Set diff
  preview, undo/redo, an in-app firmware-repository browser, a
  zip+manifest bulk-flashing workflow, and a real telemetry collection
  backend — all deliberately scoped out of this release, see that file
  for why).
- An architecture diagram and a concurrency/scale-limits table in
  `docs/DEVELOPER_DOCUMENTATION.md` §2a/§2b.
- Explicit `setAccessibleName()` calls on the new Settings controls
  above, plus a status-update in `docs/ACCESSIBILITY.md` on the current
  audit scope.

### Changed
- `docs/PRIVACY.md` rewritten to describe the new opt-in telemetry
  setting in full (previously stated flatly that no telemetry code
  existed at all).

### Fixed
- The single-instance lock file in the app-data folder is now actually
  hidden on Windows (previously named `app.lock` with no leading dot and
  never passed through the app's hide-file helper, so it sat visibly in
  the app-data folder for the entire time the app was running). Renamed
  to `.app.lock` and hidden via the same mechanism every other internal
  sidecar file already uses.
- Fixed a rare but real CI crash (`Fatal Python error: Aborted`, process
  core-dumped) around `FlashController`/`ProvisionController` finishing a
  worker: `finished_flash`/`finished_provision` is emitted from inside
  the `FlashWorker`/`ProvisionWorker` `QThread`'s `run()` a few
  instructions *before* the underlying OS thread actually exits, so the
  queued cross-thread slot that receives it could start running on the
  main thread while that thread was still finishing its teardown. With
  nothing else keeping the worker alive past that point, the
  still-finishing `QThread` could be raced by whatever ran next — the
  same class of `os.environ` race already fixed once for stall-timeout
  reads (see `FlashWorker.__init__`'s docstring), just from the
  "leftover thread" angle instead of the "read during `run()`" angle.
  Both controllers now call `worker.wait()` before continuing once a
  worker reports it's finished, closing the window by construction
  instead of relying on timing. Bounded to 5s with a logged warning (not
  a raised error) if that's ever exceeded, so a slow teardown can never
  hang the UI.

### Internal
- 57 new automated tests across the settings getters, structured JSON
  logging, diagnostics bundle export, telemetry recording, `.emfm`
  input-validation hardening, CSV import, and default-device-profile
  application — see `tests/utilities/`, `tests/project_manager/`, and
  `tests/controllers/test_device_controller.py`.
- APP_VERSION bumped to 0.14.0 in app/utilities/constants.py.

## [0.13.0] - 2026-09-07

### Added
- **Max Parallel Flashes** setting (Settings → General, default 8,
  adjustable 1–64): caps how many devices `FlashController.start_batch()`
  runs concurrently. Devices beyond the cap show a new *Queued* status
  and launch automatically as running devices finish, instead of every
  device in a batch firing its own subprocess at once.
- **Cancel Merge** button and background-thread execution for Merge
  Bins: a large or slow merge no longer freezes the application.
- `.github/workflows/version_check.yml`: fails a tagged-release build if
  `APP_VERSION` doesn't match the version markers in README.md and this
  file.
- This `CHANGELOG.md` file itself.
- `docs/PRIVACY.md` — a one-paragraph statement confirming no telemetry
  currently leaves the device.
- `docs/ACCESSIBILITY.md` — current screen-reader/accessibility
  conformance and known gaps.
- `docs/MAINTENANCE_POLICY.md` — a bus-factor/succession policy for the
  project's single-maintainer status.
- A `.emfm`/`.efmproj` deprecation notice, shown in-app and in
  `docs/USER_MANUAL.md`, stating that legacy `.efmproj` compatibility may
  be discontinued in a future release.
- A forced-save-before-risky-operation mechanism for legacy `.efmproj`
  projects, so a project opened from that format is saved back to disk
  before any operation that could otherwise lose data or leave the file
  out of sync (e.g. before closing, before switching projects).

### Changed
- `DeviceController.apply_to_all` / `apply_to_selected` /
  `apply_firmware_to_devices` now skip any device
  `FlashController.is_busy()` reports as mid-flash, instead of mutating
  it regardless. Fixes a traceability bug where renaming a device or
  reassigning its port mid-flash via Batch Edit could make the resulting
  history entry reflect the new values rather than what was actually
  flashed.
- README.md, `docs/DEVELOPER_DOCUMENTATION.md`, and
  `docs/USER_MANUAL.md` no longer describe parallel flashing as
  "unlimited" — updated to describe the new configurable cap and queue.

### Fixed
- `bin_merge`-driven merges no longer block the GUI thread for up to
  `MERGE_TIMEOUT_SECONDS` (180s) with no way to cancel.

### Internal
- Added `MergeWorker` (`app/workers/merge_worker.py`), reusing
  `FlashProcess` the same way `FlashWorker` does, so Merge Bins gets
  streamed output, cancellation, and a timeout without duplicating the
  esptool-subprocess-handling logic.
- Added test coverage for the parallel-flash cap/queue (controller-level
  and mocked-serial end-to-end), the `DeviceController` busy-device
  guard, and `MergeWorker` (success, failure, cancel, and timeout paths).
- APP_VERSION bumped to 0.13.0 in app/utilities/constants.py.
