"""Confirmations before a command that changes the cluster (spec 69 R4.4): what runs, where, exactly."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.remote.submit import SubmitPlan
from ...i18n import _
from ..widgets.common import set_variant


class SubmitDialog(QDialog):
    """ "Submeter {script}?": the folder, the commands as they go to ssh and a warning per
    forgotten ``EXIT``. With a warning, Enter cancels."""

    def __init__(self, plan: SubmitPlan, account: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_("Submeter no cluster"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        title = _("Submeter {script}?").format(script=plan.script)
        layout.addWidget(set_variant(QLabel(title), "dialogTitle"))
        folder = _("Pasta: {account}:{folder}").format(account=account, folder=plan.remote_dir)
        layout.addWidget(set_variant(QLabel(folder), "dialogText"))
        layout.addWidget(set_variant(QLabel(_("Comandos que vão rodar no cluster:")), "dialogText"))
        self.commands = set_variant(QLabel("\n".join(plan.steps)), "mono")
        layout.addWidget(self.commands)
        self.warnings = []
        for name in plan.exit_files:
            text = _(
                "A pasta tem {name}: o pw.x vai parar na primeira verificação. Apague o arquivo no "
                "cluster antes de submeter."
            ).format(name=name)
            label = set_variant(QLabel(text), "warning")
            label.setWordWrap(True)
            self.warnings.append(label)
            layout.addWidget(label)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton(_("Cancelar"))
        self.submit_button = set_variant(QPushButton(_("Submeter")), "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.submit_button.clicked.connect(self.accept)
        (self.cancel_button if self.warnings else self.submit_button).setDefault(True)
        row.addWidget(self.cancel_button)
        row.addWidget(self.submit_button)
        layout.addLayout(row)


def ask_submit(parent: QWidget, plan: SubmitPlan, account: str) -> bool:
    """True when the user confirmed the submission."""
    dialog = SubmitDialog(plan, account, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted
