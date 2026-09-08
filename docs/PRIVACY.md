# Privacy Statement

ESP32 Multi Flash Manager does not collect, transmit, or store any
telemetry, analytics, crash reports, or usage data about you or your
device **unless you explicitly opt in** (Settings → Privacy → "Share
anonymous usage & crash data"). This setting is **off by default**.

## What stays local, always

Everything the app writes in its normal operation — project files, the
four rotating log files, the optional structured `events.jsonl` log,
history entries, the crash-recovery autosave slot, saved Firmware
Profiles — stays on disk, locally, under your control, and is never sent
anywhere by this app. The only network activity performed without your
explicit action elsewhere in the app is the optional, user-initiated
update check (Tools → Check for Updates...), which contacts GitHub's
public releases API to compare version numbers and does not transmit
anything about you, your project, or your devices.

## What the opt-in telemetry setting does

When you turn on Settings → Privacy → "Share anonymous usage & crash
data", the app begins recording a small, fixed set of coarse events
locally to `telemetry_events.jsonl` under the app-data folder (see
Diagnostics → "Open Logs Folder" for that folder's location on your
machine). Each recorded event contains:

- a random, per-install client ID generated the first time telemetry is
  enabled (not derived from your name, hostname, MAC address, or
  anything else identifying)
- one of a fixed, reviewed set of event names — e.g. "the app started",
  "a flash batch finished," "a provisioning batch finished," "a project
  was opened/saved," "an unhandled exception occurred"
- a small set of event-specific counters or booleans (for example, a
  device count and a success/failure count for a finished batch)
- a UTC timestamp

**Recorded events never include:** device serial numbers, COM port
names, firmware file names or paths, project file names or paths,
firmware/eFuse contents, or any other value that could identify a
specific person, device, or the content being flashed.

## What this build does *not* do with that data

As of this release, telemetry events are written **locally only**.
Nothing is transmitted over the network by this build, even with the
setting turned on — there is no telemetry collection backend configured
or contacted. This is a deliberate, disclosed limitation: shipping a
real collection endpoint is a separate decision (choosing/standing up
infrastructure, a retention policy, and a corresponding update to this
document describing exactly where data goes) that is intentionally out
of scope for this release. See `ROADMAP.md` for that future work. The
single call site (`app.utilities.telemetry.record_event`) that a future
release would extend to also transmit these events is documented in
that module's docstring.

## Managing telemetry data

- **Turn it off:** Settings → Privacy → uncheck "Share anonymous usage &
  crash data". No further events are recorded after this.
- **Delete what's been recorded:** Settings → Privacy → "Clear Local
  Telemetry Data" deletes `telemetry_events.jsonl` immediately.
- **Inspect what's been recorded:** the file is plain, human-readable
  JSON Lines — open it in any text editor via Diagnostics → "Open Logs
  Folder".

## Diagnostics bundle export

Help → "Export Diagnostics Bundle..." (or Settings → Diagnostics) lets
you manually save a `.zip` containing your current log files plus
app/OS/Python/esptool version information, for attaching to a bug
report. This is a manual, explicit, one-shot export you trigger and save
wherever you choose — it is unrelated to the telemetry setting above,
never runs on its own, and nothing is uploaded anywhere by this app.
