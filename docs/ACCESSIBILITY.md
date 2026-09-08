# Accessibility Statement

## Current conformance level

ESP32 Multi Flash Manager is a PySide6 (Qt) desktop application and
inherits Qt's baseline accessibility support: standard widgets (buttons,
labels, checkboxes, menus, dialogs, tables) expose their visible text to
screen readers via each platform's native accessibility API (e.g. Narrator
on Windows, VoiceOver on macOS, Orca on Linux) without any extra work on
our part, standard keyboard navigation (Tab/Shift+Tab, arrow keys inside
lists/tables, Enter/Escape in dialogs) works throughout, and every
customizable action's keyboard shortcut can be remapped from Tools →
Keyboard Shortcuts... for anyone who finds the defaults hard to reach or
memorize.

We have not yet performed a dedicated screen-reader audit. As of this
release, the newly-added Settings controls (Advanced, Diagnostics, and
Privacy tabs — see `CHANGELOG.md`) have explicit `setAccessibleName()`
calls beyond what Qt infers automatically from widget text, since a
`QFormLayout` label is not always reliably associated with its field by
every screen reader. The rest of the application's widgets rely on Qt's
automatic inference, as described below, and have not yet been
individually audited.

Beyond that incremental pass, this document reflects our current
starting point honestly rather than claiming a conformance level (e.g.
WCAG 2.1 AA) we haven't verified.

## Known gaps

- **Icon-only controls.** A handful of toolbar/table actions are
  icon-only with a tooltip but no explicit accessible name set, so a
  screen reader may announce them only by their Qt object name (or not
  at all) rather than by their visible tooltip text.
- **Status badges and color coding.** Device status (Waiting, Queued,
  Uploading, Failed, etc.) is communicated partly through background
  color (see `STATUS_COLORS` in `app/utilities/constants.py`) alongside
  its text label. The text label is always present, but the color
  coding itself has not been verified against color-blindness-safe
  palettes.
- **Custom-painted widgets.** A few widgets (e.g. progress indicators,
  the interface-lock overlay) are custom-painted rather than built from
  a single standard Qt widget, and their accessible names/roles have
  not been individually audited.
- **No automated accessibility testing.** The test suite does not
  currently include any screen-reader or accessibility-tree assertions,
  so regressions here would not be caught by CI.

## Reporting a gap

If you rely on assistive technology and hit a specific barrier using
this app, please open a GitHub issue describing what you were trying to
do, which assistive technology/platform you're using, and what
happened — accessibility issues are treated the same as any other bug
report.
