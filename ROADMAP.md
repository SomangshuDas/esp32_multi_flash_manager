# Roadmap

This document tracks larger, self-contained features that are planned
but were deliberately **not** included in the current release, along
with the design thinking behind each so a future contributor (or a
future release) has a starting point rather than a blank slate. Smaller,
already-shipped improvements are tracked in `CHANGELOG.md` instead.

Items here are roughly ordered by how self-contained/ready-to-build they
are, not by priority.

> Four entries that used to live here — dry-run/pre-flight simulation,
> the Batch Edit / Assign Firmware Set diff-preview step, undo/redo for
> mutating operations, and the zip + manifest bulk-flashing workflow —
> shipped in 0.15.0. See `CHANGELOG.md`'s `[0.15.0]` entry for what was
> actually built.

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
what GitHub's API already provides. Deliberately not attempted alongside
the zip+manifest import in 0.15.0: unlike that feature (a purely local,
already-trusted file the operator chose themselves), this one has a real
trust-model decision — which remote repositories/publishers to treat as
safe to pull binaries from, by default or otherwise — that's a product
call for a maintainer to make explicitly, not something to bake into
code without that decision having been made first.

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
dialog in a previous release (see `docs/ACCESSIBILITY.md`).

**Design sketch:** no code changes required to start — this is testing
effort more than design work. `docs/ACCESSIBILITY.md`'s "Known gaps"
section is the checklist to work through.
