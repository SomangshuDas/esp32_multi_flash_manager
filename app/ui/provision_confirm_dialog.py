"""
provision_confirm_dialog.py
============================
Explicit, hard-to-fat-finger confirmation gate shown before ANY eFuse-
burning operation (flash encryption key, secure boot key digest, or any
other eFuse write). Burning eFuses on real hardware is a one-way,
irreversible operation -- getting past this dialog requires both:

  1. Checking an "I understand this is irreversible" checkbox, AND
  2. Typing the exact confirmation phrase (PROVISION_CONFIRM_PHRASE) into
     a text field.

This is the risk surfaced "prominently in the UI, not just the
documentation" -- the actual requirement this dialog exists to satisfy.
Only after this dialog returns Accepted does the caller wire the
`--do-not-confirm` flag into the espefuse commands it runs (that flag
skips espefuse's own interactive terminal prompt, which would otherwise
hang forever against this app's piped subprocess -- it is not a
replacement for this dialog, this dialog is the actual confirmation).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.utilities.constants import PROVISION_CONFIRM_PHRASE


class ProvisionConfirmDialog(QDialog):
    """Returns True from confirm_burn(...) only if the user both checked
    the acknowledgement box AND typed the exact confirmation phrase (and,
    when `show_backup_reminder` is set, also checked the key-backup
    acknowledgement)."""

    def __init__(self, summary_lines: list[str], parent=None, *, show_backup_reminder: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Irreversible eFuse Operation")
        self.setMinimumWidth(480)
        self._show_backup_reminder = show_backup_reminder

        layout = QVBoxLayout(self)

        warning = QLabel(
            "<b style='color:#e03131;'>&#9888; This will permanently burn eFuses on real "
            "hardware.</b><br>eFuses cannot be un-burned. A mistake here (wrong key, wrong "
            "device, wrong mode) can make the device impossible to re-flash normally, or "
            "permanently lock it out of plain (unencrypted/unsigned) firmware forever."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        if summary_lines:
            summary_label = QLabel("About to run:<br>" + "<br>".join(f"&bull; {line}" for line in summary_lines))
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet("margin-top: 8px;")
            layout.addWidget(summary_label)

        self.ack_checkbox = QCheckBox(
            "I understand this operation is irreversible and have verified the device, "
            "chip type, and key are correct."
        )
        self.ack_checkbox.setStyleSheet("margin-top: 12px;")
        self.ack_checkbox.toggled.connect(self._update_ok_enabled)
        layout.addWidget(self.ack_checkbox)

        self.backup_ack_checkbox = None
        if show_backup_reminder:
            # A key with key_source == "generate" only exists as this one
            # local file (plus, optionally, an OS-keychain copy -- see
            # SecurityConfig.store_keys_in_os_keychain) until the user
            # backs it up themselves. If it's lost after the eFuse burn
            # below, the device is permanently locked out of any future
            # re-flash/re-provisioning with a *different* key -- this
            # reminder exists so that's a deliberate, acknowledged risk
            # rather than a surprise discovered after the fact.
            backup_note = QLabel(
                "<b>Before burning:</b> the generated key file is the ONLY copy of this key. "
                "Losing it after burning means this device can never be re-flashed with a "
                "different key. Back it up to a safe, separate location now."
            )
            backup_note.setWordWrap(True)
            backup_note.setStyleSheet("margin-top: 10px; color: #e8590c;")
            layout.addWidget(backup_note)

            self.backup_ack_checkbox = QCheckBox("I have backed up the generated key file(s) to a safe location.")
            self.backup_ack_checkbox.toggled.connect(self._update_ok_enabled)
            layout.addWidget(self.backup_ack_checkbox)

        phrase_label = QLabel(f"Type <b>{PROVISION_CONFIRM_PHRASE}</b> below to confirm:")
        phrase_label.setStyleSheet("margin-top: 8px;")
        layout.addWidget(phrase_label)

        self.phrase_edit = QLineEdit()
        self.phrase_edit.setPlaceholderText(PROVISION_CONFIRM_PHRASE)
        self.phrase_edit.textChanged.connect(self._update_ok_enabled)
        layout.addWidget(self.phrase_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Burn eFuses")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("background-color: #e03131; color: white;")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._update_ok_enabled()

    def _update_ok_enabled(self, *_args) -> None:
        ready = self.ack_checkbox.isChecked() and self.phrase_edit.text().strip() == PROVISION_CONFIRM_PHRASE
        if self.backup_ack_checkbox is not None:
            ready = ready and self.backup_ack_checkbox.isChecked()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ready)


def confirm_irreversible_burn(parent, summary_lines: list[str], *, show_backup_reminder: bool = False) -> bool:
    """Convenience wrapper: show the dialog and return whether the user
    completed every required confirmation step and accepted."""
    dialog = ProvisionConfirmDialog(summary_lines, parent, show_backup_reminder=show_backup_reminder)
    return dialog.exec() == QDialog.DialogCode.Accepted
