# Contributing to ESP32 Multi Flash Manager

Thanks for considering a contribution! This project is maintained by a
single author in the open, so clear, focused pull requests are the
fastest path to getting something merged. Please also read the
[Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Before you start

- For anything beyond a small fix, please open an issue first describing
  what you'd like to change and why — this avoids duplicated effort and
  lets us agree on the approach before you invest time in an
  implementation.
- Read [`docs/DEVELOPER_DOCUMENTATION.md`](docs/DEVELOPER_DOCUMENTATION.md)
  first. It documents the architecture (strict MVC, out-of-process
  `esptool`/`espefuse`/`espsecure`, one `QThread` per device, etc.) and
  the specific conventions this codebase follows — matching them makes
  review much faster.

## Development setup

```bash
git clone https://github.com/SomangshuDas/esp32_multi_flash_manager.git
cd esp32_multi_flash_manager
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python run.py
```

## Conventions this codebase follows

Please match these patterns rather than introducing new ones, unless
your PR is specifically about changing the pattern itself:

- **Strict MVC.** Models never import Qt. Controllers never import
  concrete widgets. Views only ever call controllers, never
  `flash_engine`/`project_manager`/`firmware_manager`/`device_manager`
  directly.
- **Out-of-process tooling.** `esptool`, `espefuse`, and `espsecure` are
  always invoked as subprocesses, never imported and called in-process.
  This project deliberately never reimplements any part of the ESP32
  flashing/eFuse/crypto protocol itself — all of that logic belongs
  upstream in those tools.
- **Synchronous vs. threaded operations.** A quick, single-connection
  read (Chip Info, Flash ID, eFuse Summary) can run synchronously,
  following the `bin_merge.py` pattern. Anything that could take a while
  or block the UI (flashing, Read Flash, eFuse burning) must run in its
  own `QThread` worker with its own signals.
- **Irreversibility safeguards.** Any operation that's permanent on real
  hardware (burning an eFuse, an encrypted flash write) must be gated
  behind an explicit confirmation dialog — not just a settings toggle —
  before it's ever queued.
- **Distinct labels for meaningfully different operations.** e.g.
  "Encrypted Write Flash" vs. "Write Flash" in logs/history — don't
  collapse operations with materially different consequences into one
  label with a footnote.
- **Paired `validate_*`/`run_*` functions** in backend modules, so
  pre-flight validation stays testable independently of execution.
- **Errors block, warnings require confirmation** — keep this UX
  distinction consistent across any new validation you add.

## Testing your change

There's no bundled test suite yet (see §7 of the developer docs for
why, and what a good addition would look like), but at minimum, before
opening a PR:

1. **Syntax-check** every file you touched:
   ```bash
   python -c "import ast; ast.parse(open('path/to/file.py').read())"
   ```
2. **Import-test headlessly** (catches missing imports/circular imports
   without needing a display):
   ```bash
   QT_QPA_PLATFORM=offscreen python -c "import app.ui.your_module"
   ```
3. If your change touches `espefuse`/eFuse logic, verify it against
   `espefuse`'s own `--virt` (virtual/no-hardware) mode where possible,
   rather than only against real hardware.
4. If your change touches packaging (`packaging/windows`,
   `packaging/linux`, `packaging/macos`), make sure any new
   dependency data files are covered by the appropriate
   `--collect-all` flag — see `docs/BUILD_INSTRUCTIONS.md` for why
   `espefuse` in particular needs its own explicit `--collect-all`
   despite shipping in the same PyPI wheel as `esptool`.

## Submitting a pull request

- Keep PRs focused — one feature or fix per PR is much easier to review
  than a bundle of unrelated changes.
- **Update documentation in the same PR as the code it describes.**
  If you change behavior, update the relevant section of
  `README.md`, `docs/USER_MANUAL.md`, or `docs/DEVELOPER_DOCUMENTATION.md`
  — don't leave docs to a follow-up.
- If your change is user-facing, mention it in your PR description in a
  way that could be dropped into a release note.
- Never commit real flash-encryption keys, secure-boot signing keys, or
  eFuse dumps from real hardware — use `espefuse`'s virtual mode or
  clearly-fake placeholder data in any test fixtures or screenshots.

## Reporting bugs

Please include:

- Your OS and Python version.
- Your installed `esptool` version (`pip show esptool`).
- Steps to reproduce.
- Relevant log excerpts from the app's rotating log files (see §8 of the
  developer docs for their location) — with any real MAC addresses, key
  material, or eFuse dumps redacted first.

For anything that looks like a security issue rather than a regular bug
(e.g. a way to bypass the eFuse-burning confirmation dialog), please
follow [`SECURITY.md`](SECURITY.md) instead of opening a public issue.

## License

By contributing, you agree that your contributions will be licensed
under this project's [MIT License](LICENSE).
