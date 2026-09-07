<!-- APP_VERSION: 0.13.0 -->
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

## [0.13.0] - 2026-09-06

### Added
- **Max Parallel Flashes** setting (Settings → General, default 8,
  adjustable 1–64): caps how many devices `FlashController.start_batch()`
  runs concurrently. Devices beyond the cap show a new *Queued* status
  and launch automatically as running devices finish, instead of every
  device in a batch firing its own subprocess at once.
- **Cancel Merge** button and background-thread execution for Merge
  Bins: a large or slow merge no longer freezes the application.
- `.github/dependabot.yml` to automate dependency-update pull requests
  for both `pip` (`requirements.txt`/`requirements-dev.txt`) and
  `github-actions` (workflow action versions).
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
