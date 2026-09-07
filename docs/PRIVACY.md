# Privacy Statement

ESP32 Multi Flash Manager does not collect, transmit, or store any
telemetry, analytics, crash reports, or usage data about you or your
device outside of your own machine. There is currently no
network-connected telemetry code anywhere in this codebase — everything
the app writes (project files, logs, history entries, the crash-recovery
autosave slot) stays on disk, locally, under your control, and is never
sent anywhere. The only network activity the app performs is the
optional, user-initiated update check (Tools → Check for Updates...),
which contacts GitHub's public releases API to compare version numbers
and does not transmit anything about you, your project, or your devices.

If an opt-in, anonymous telemetry feature is added in a future release
(see the "Observability and Diagnostics" section of the project's
requirements/roadmap), it will be off by default, clearly disclosed, and
this statement will be updated to describe exactly what it collects
before that release ships.
