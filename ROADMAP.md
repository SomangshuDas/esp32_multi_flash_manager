# Roadmap

This document tracks larger, self-contained features that are planned
but were deliberately **not** included in the current release, along
with the design thinking behind each so a future contributor (or a
future release) has a starting point rather than a blank slate. Smaller,
already-shipped improvements are tracked in `CHANGELOG.md` instead.

Items here are roughly ordered by how self-contained/ready-to-build they
are, not by priority.

## Dry-run / pre-flight simulation mode

**What it would do:** run every check the flashing pipeline normally
performs — port availability, duplicate/overlapping firmware addresses,
chip-compatibility warnings (`app/flash_engine/validator.py`), missing
firmware files — against the whole current device list **without**
requiring any device to actually be connected, so an operator can
validate a bench configuration (or review a project file someone else
built) before the hardware is even on the desk.

**Design sketch:** `ValidationReport` already exists and is
connection-independent for everything except live port availability;
the main work is a "Validate Bench (Dry Run)" entry under the Tools menu
that runs `validator.py` against every device regardless of `com_port`
being currently enumerated, and a dialog presenting the aggregated
report (reusing the existing validation-report UI rather than a new
one).

## Diff / preview step for Batch Edit and Assign Firmware Set

**What it would do:** before applying a Batch Edit or an Assign Firmware
Set operation across many devices, show a before/after summary (which
devices change, from what value to what value) with a final
confirm/cancel, the same way the eFuse-burning confirmation gate works
today for provisioning.

**Design sketch:** both dialogs already compute the full set of target
devices and the new value before calling into `DeviceController`; the
new step is inserting a read-only "N devices will change X from A to B"
table between "OK" and the actual mutation, reusing
`BatchProvisionDialog`'s confirmation-dialog pattern as a template.

## Undo/redo for mutating operations

**What it would do:** Ctrl+Z / Ctrl+Y (or Cmd+Z / Cmd+Shift+Z on macOS)
undo/redo coverage for device mutations — Batch Edit, bulk delete,
Assign Firmware Set, CSV import — the way most desktop apps handle
accidental bulk changes.

**Design sketch:** the natural shape is a small command stack living on
`ProjectController` (`push(before_state, after_state, description)`,
`undo()`, `redo()`) operating on whole-device snapshots rather than
field-level diffs, since `DeviceConfig` is a plain dataclass that's
cheap to deep-copy — much simpler to implement correctly than a
generic-diff/patch system, at the cost of somewhat more memory per undo
step (acceptable given realistic device-list sizes, see
`MAX_DEVICES_PER_PROJECT` in `docs/THREAT_MODEL.md`). Scoping this to
the four operations above (not every single-field edit in the Device
Settings panel) keeps the first version small and would be extended
incrementally.

## In-app firmware-repository browser

**What it would do:** browse and pull firmware binaries directly from a
configured GitHub Releases repository (or similar) from inside the app,
instead of the operator downloading a `.bin` externally and pointing
"Add Firmware" at it.

**Design sketch:** `app/utilities/update_checker.py` already implements
the GitHub Releases API polling and asset-selection pattern this would
reuse (auth-free public API calls, asset filtering, download-with-
progress); the new pieces are a repository-picker (or a configured
default in Settings), a release/asset browser dialog, and wiring a
downloaded asset into the existing `FirmwareEntry` flow. Scope
questions to resolve before building this: which repositories are
trusted by default (none, requiring explicit configuration, seems
safest), and whether downloaded binaries get any integrity check beyond
what GitHub's API already provides.

## Zip + manifest bulk-flashing workflow

**What it would do:** accept a single `.zip` containing firmware
binaries plus a manifest file (device name/tag → firmware+address
mapping) and materialize it into a full device list + firmware
assignment in one import step — useful for shipping "everything needed
for this production run" as one file to a remote operator.

**Design sketch:** conceptually an extension of `csv_import.py` (this
release) plus `firmware_manager/auto_detect.py`'s folder-to-firmware-list
logic: unzip to a temp directory, parse the manifest (a natural fit for
either CSV or JSON), resolve each manifest firmware reference against
the unzipped files, and reuse `import_devices_from_csv`'s row error model
for reporting problems per manifest entry. The main open design question
is the manifest format itself — worth reviewing with real production
CSV/manifest examples from actual users before locking anything in,
rather than guessing.

## Telemetry collection backend

**What it would do:** actually transmit the locally-recorded, opt-in
telemetry events (see `docs/PRIVACY.md`, `app/utilities/telemetry.py`)
to a real collection endpoint instead of only writing them locally.

**Why this is separate from "add telemetry" (already shipped):**
standing up a backend is an infrastructure and policy decision (hosting,
retention period, who has access to the data, a public disclosure of
exactly where it goes) that shouldn't be bundled into the same change
that added the opt-in toggle and local recording. `record_event()` in
`app/utilities/telemetry.py` is the single call site a future release
would extend to also POST the same payload to a configured endpoint.

## Accessibility: full screen-reader audit

**What it would do:** a dedicated pass with an actual screen reader
(NVDA/Narrator/VoiceOver/Orca) against every dialog and panel, beyond
the incremental `setAccessibleName()` additions made to the Settings
dialog in this release (see `docs/ACCESSIBILITY.md`).

**Design sketch:** no code changes required to start — this is testing
effort more than design work. `docs/ACCESSIBILITY.md`'s "Known gaps"
section is the checklist to work through.
