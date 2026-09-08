# Frequently Asked Questions

A quick-reference companion to `docs/USER_MANUAL.md` §24
"Troubleshooting" — that section covers step-by-step fixes for specific
symptoms; this page answers the shorter questions that come up before
you've hit a problem.

**Q: How many devices can I flash at once?**
Up to **Max Parallel Flashes** (Settings → General, default 8, adjustable
1–64). Add more devices than that and the extras show a *Queued* status,
starting automatically as running ones finish — you don't need to split
a large batch into smaller ones by hand.

**Q: What about batch provisioning (eFuse burning)?**
Same idea, its own cap: **Max Parallel Provisions** (Settings → General
→ Provisioning, default 8, adjustable 1–32).

**Q: Is there a limit on how many devices a project file can hold?**
2000 devices per project, 200 firmware entries per device — see
`docs/THREAT_MODEL.md` for why these exist (they're input-validation
bounds for opening untrusted `.emfm` files, not a UX limit; no real bench
gets anywhere near them).

**Q: Does this app phone home / send any data anywhere?**
No, unless you explicitly turn on Settings → Privacy → "Share anonymous
usage & crash data" (off by default) — and even then, this build only
writes events locally, it doesn't transmit them anywhere. See
`docs/PRIVACY.md` for the full statement.

**Q: How do I get logs to attach to a bug report?**
Help → **Export Diagnostics Bundle...** saves one `.zip` with all
current logs plus app/OS/Python/`esptool` version info — easier than
attaching four separate log files by hand. Settings → Diagnostics has
the same button, plus a plain "Open Logs Folder" if you'd rather grab
files individually.

**Q: Can I bulk-add devices instead of clicking "Add Device" many times?**
Yes — **Devices → Import Devices from CSV...**. Only a `name` column is
required; `com_port`, `chip_type`, `baud_rate`, and `tags` are optional.
See `docs/USER_MANUAL.md` §10 for the exact format.

**Q: I set a "Default Device Profile" — what exactly does that do?**
Every newly-added device (via "Add Device" or CSV import) has that
saved Firmware Profile's chip/flash settings and firmware list applied
automatically, instead of the app's built-in defaults. Set it (or leave
it on "none") in Settings → General.

**Q: A project file I received from someone else won't open — is that
expected?**
If it reports being corrupted, oversized, or listing an implausible
number of devices, that's the app's input-validation catching a bad or
malicious file rather than silently trying to load it — see
`docs/THREAT_MODEL.md`. If you believe a legitimate project file is
being rejected, please open a GitHub issue with (a sanitized copy of,
see `SECURITY.md`) the file.

**Q: Where do I report a security issue vs. a regular bug?**
Security issues (anything that could leak key material, corrupt eFuses
unexpectedly, or execute code via a crafted project file) → follow
`SECURITY.md`'s private disclosure process, not a public issue. Anything
else → a regular GitHub issue is fine.
