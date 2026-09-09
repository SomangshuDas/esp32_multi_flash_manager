# Threat Model: `.emfm` Project File Parsing

This document scopes the trust boundary around `.emfm` project files —
the plain-JSON format read by "Open Project" and written by "Save
Project" (`app/project_manager/project_io.py`) — and the input
validation added to defend it.

## Why this file format is in scope

A `.emfm` file is **untrusted input** the moment it can arrive from
outside the machine that created it: email attachments, a USB stick
handed between operators on a manufacturing floor, a shared network
drive, a project shared over chat, or simply a file a well-meaning
operator renamed by hand. "Open Project" will parse whatever is pointed
at it. That makes the parser a real attack surface, distinct from (and
much smaller than) e.g. a web service parsing untrusted input from the
internet — but the same discipline applies at a smaller scale.

## Assets and goals

What we're protecting:

1. **Availability of the operator's machine/session** — a hostile or
   corrupted file should never be able to hang the UI thread indefinitely
   or exhaust available memory just by being opened.
2. **Confidentiality/integrity of the filesystem** — a project file
   should not be able to make the app read or write files outside what
   the operator explicitly intended.
3. **Predictable failure** — a bad file should fail fast with a clear,
   friendly `ProjectLoadError`, never an unhandled exception or a silent
   partial load that surprises the operator later.

Explicitly **not** goals:

- Defending against a threat actor with write access to the app's own
  settings.json or app-data folder (that's a stronger privilege than
  crafting a `.emfm` file; if they can write there, `.emfm` parsing
  isn't the weakest link).
- Sandboxing or validating the *firmware binaries* a project references
  — those are handled (checksummed via `compute_md5`, size-reported) by
  the flashing pipeline and esptool, not by project-file parsing.

## Threats considered and mitigations

| Threat | Mitigation |
| --- | --- |
| **Malformed / non-UTF-8 / non-JSON file** (binary garbage, or an unrelated file renamed to `.emfm`) | `load_project()` catches `OSError`/`ValueError` (which covers `json.JSONDecodeError` and `UnicodeDecodeError`) around the parse and raises a friendly `ProjectLoadError` instead of leaking a raw traceback into the UI. |
| **Extremely large file ("JSON bomb" via sheer size)** | `MAX_PROJECT_FILE_SIZE_BYTES` (25 MiB) is checked against `Path.stat().st_size` **before** `json.load()` ever runs, so a multi-gigabyte file is rejected without the cost of parsing it first. |
| **Pathologically large `"devices"` array** (e.g. millions of entries, technically valid JSON) | `_validate_project_shape()` checks `len(devices)` against `MAX_DEVICES_PER_PROJECT` (2000) immediately after parsing, before any `DeviceConfig` objects are constructed or handed to the UI to render. |
| **Pathologically large `"firmware"` array on a single device** | Same function checks each device's `firmware` list length against `MAX_FIRMWARE_ENTRIES_PER_DEVICE` (200). |
| **Wrong-typed fields** (e.g. `"devices"` is a string, or a device entry is `null`) | Left to `ProjectModel.from_dict()`, which is already defensive about type mismatches and raises a `ProjectLoadError` with a readable message rather than crashing; `_validate_project_shape()` deliberately does not duplicate that type-checking, only the size caps that `from_dict()` has no natural place to enforce cheaply before construction. |
| **Firmware `file_path` pointing outside the project directory** (e.g. `"../../../etc/passwd"`, or an absolute path to an arbitrary file) | **Not blocked**, by design. Firmware files legitimately live anywhere the operator's filesystem permissions allow — a shared firmware repository outside the project folder is a normal, supported layout (see `_absolutize_firmware_paths`'s docstring). The app only ever *reads* the referenced file (to compute its size/MD5 and pass its path to `esptool`) using the operator's own OS-level file permissions; it never uses a project file's paths to *write* outside a location the operator explicitly chose (Save/Save As, Bin Merge output location, Export...). This is a conscious trade-off: restricting firmware paths to "inside the project folder" would break a common, legitimate workflow (a shared network firmware repo referenced by many project files) for a protection that doesn't add much, since the same operator opening the project already has read access to whatever the path points at.
| **Symlink / junction firmware paths** | Same reasoning as above — not specially restricted, since the operation performed (read a file, report its size/hash, hand its path to esptool) is the same class of access the operator already has directly. |
| **Resource exhaustion via the *autosave recovery* slot** (`AUTOSAVE_RECOVERY_DIRNAME`) | Lower risk: that file is written only by this app itself into its own app-data folder, not accepted as arbitrary input from another party, so it is out of scope for these caps (see "Explicitly not goals" above). |

## Reporting a vulnerability

See `SECURITY.md` at the repository root for the disclosure process.

## Zip + manifest firmware bundle import

`Devices → Import Firmware Bundle (.zip)...`
(`app/project_manager/zip_manifest_import.py`) accepts the same class of
untrusted input as a `.emfm` project file (see "Why this file format is
in scope" above) — a `.zip` can arrive from anywhere a project file can.
The mitigations mirror the ones above, applied to an archive instead of
a JSON document:

| Threat | Mitigation |
| --- | --- |
| **Extremely large bundle** | `MAX_ZIP_BUNDLE_SIZE_BYTES` (200 MiB) is checked against the archive's total *uncompressed* size (summed from `ZipInfo.file_size` across every member) before any member is extracted. |
| **"Zip slip" (a member path like `../../evil.bin` or an absolute path escaping the extraction folder)** | `_safe_extract_all()` resolves each member's target path and refuses (raises `ZipManifestImportError`, aborting the whole import) any entry whose resolved path would land outside the bundle's own extraction directory, rather than silently skipping just that one entry. |
| **Pathologically large manifest** (thousands of rows) | `MAX_ZIP_MANIFEST_ROWS` (5000) stops parsing further rows once reached, reporting how many were ignored, instead of building an unbounded device list. |
| **Corrupt / not-actually-a-zip file** | `zipfile.BadZipFile` is caught and re-raised as a friendly `ZipManifestImportError`. |
| **Manifest referencing a firmware file not actually in the bundle** | Reported as a per-row error (`ZipManifestImportResult.errors`), not a fatal failure — the rest of the manifest still imports, same as a bad CSV device-import row. |

Explicitly not a goal here either: validating the *firmware binaries*
themselves — same reasoning as `.emfm` firmware references above, this
is handled by the flashing pipeline/esptool, not by the import step.
