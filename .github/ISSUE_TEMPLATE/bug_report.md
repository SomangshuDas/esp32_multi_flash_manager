---
name: Bug report
about: Something isn't working the way it should
title: "[Bug] "
labels: bug
assignees: ''
---

**Describe the bug**
A clear, concise description of what went wrong.

**To reproduce**
Steps to reproduce the behavior, e.g.:
1. Configure device with '...'
2. Click '...'
3. See error

**Expected behavior**
What you expected to happen instead.

**Environment**
- OS: [e.g. Windows 11, Ubuntu 24.04, macOS 14]
- App version: [`Help → About`, or the value of `APP_VERSION` in
  `app/utilities/constants.py` if running from source]
- Installed via: [installer / portable binary / running from source]
- `esptool` version: [`pip show esptool`, if running from source]

**Logs**
Attach the relevant excerpt from the app's rotating log files (see §8 of
`docs/DEVELOPER_DOCUMENTATION.md` for their location).

> ⚠️ **Before attaching logs or screenshots, please redact:** real device
> MAC addresses, flash-encryption keys, secure-boot signing keys, and
> eFuse dump contents. If this looks like a security issue rather than a
> regular bug, please use [`SECURITY.md`](../../SECURITY.md) instead of a
> public issue.

**Additional context**
Anything else relevant — a `.efmproj` file (with paths/keys redacted),
firmware layout, chip type, etc.
