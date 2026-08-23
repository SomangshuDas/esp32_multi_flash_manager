## Summary

Briefly describe what this PR changes and why.

## Related issue

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation only
- [ ] Packaging / CI
- [ ] Other (describe above)

## Checklist

- [ ] I read [`CONTRIBUTING.md`](../CONTRIBUTING.md) and followed the
      conventions there (strict MVC, out-of-process `esptool`/`espefuse`/
      `espsecure`, sync-vs-threaded rules, irreversibility safeguards for
      anything permanent on real hardware).
- [ ] I updated documentation (`README.md`, `docs/USER_MANUAL.md`, and/or
      `docs/DEVELOPER_DOCUMENTATION.md`) in this same PR, if this change
      affects user-facing behavior or architecture.
- [ ] I bumped `APP_VERSION` in `app/utilities/constants.py` and checked
      for other illustrative version strings that needed updating too, if
      this change warrants a version bump.
- [ ] Every file I touched passes `python -c "import ast; ast.parse(...)"`
      and imports cleanly with `QT_QPA_PLATFORM=offscreen`.
- [ ] I did not commit any real flash-encryption keys, secure-boot
      signing keys, eFuse dumps, or device MAC addresses.

## Testing performed

Describe how you tested this (real hardware + chip type, `espefuse
--virt`, headless import test, etc.).
