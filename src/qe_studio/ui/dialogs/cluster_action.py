"""Confirmations before a command that changes the cluster (spec 69 R4.4, spec 70 R6, spec 71 R3):
what runs, where, exactly, and a job of the same name already on the cluster."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.cluster_jobs import Job
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
        if plan.job_name:
            job = _("Job: {name}").format(name=plan.job_name)
            layout.addWidget(set_variant(QLabel(job), "dialogText"))
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


class SameNameDialog(QDialog):
    """A job of the user with the script's name is already running or waiting: one row per job and
    "Submeter outro job com o mesmo nome?". "Voltar" is the default: Enter submits nothing."""

    def __init__(self, name: str, jobs: Sequence[Job], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_("Job com o mesmo nome"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        title = _("Já existe um job seu chamado {name} no cluster").format(name=name)
        layout.addWidget(set_variant(QLabel(title), "dialogTitle"))
        form = QFormLayout()
        self.rows: list[QLabel] = []
        for job in jobs:
            if job.running:
                state = _("em execução desde {date}").format(date=job.date)
            else:
                state = _("na fila desde {date}").format(date=job.date)
            shown = QLabel(state)
            self.rows.append(shown)
            label = _("Job {job_id}").format(job_id=job.job_id)
            form.addRow(set_variant(QLabel(label), "dialogText"), shown)
        layout.addLayout(form)
        question = QLabel(_("Submeter outro job com o mesmo nome?"))
        layout.addWidget(set_variant(question, "dialogText"))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = QPushButton(_("Voltar"))
        self.go_button = QPushButton(_("Submeter mesmo assim"))
        self.back_button.clicked.connect(self.reject)
        self.go_button.clicked.connect(self.accept)
        self.go_button.setAutoDefault(False)  # focused, it would take Enter
        self.back_button.setDefault(True)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.go_button)
        layout.addLayout(buttons)
        self.back_button.setFocus()


def ask_same_name(parent: QWidget, name: str, jobs: Sequence[Job]) -> bool:
    """True when the user wants another job called ``name`` all the same."""
    dialog = SameNameDialog(name, jobs, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted


class CancelDialog(QDialog):
    """ "Cancelar esta simulação?": a block of label and value per job, the method (to read, not to
    choose), what it does and the exact command. "Voltar" is the default: Enter cancels nothing."""

    def __init__(
        self,
        rows: Sequence[Sequence[tuple[str, str]]],
        method: str,
        note: str,
        line: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(_("Cancelar simulação"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel(_("Cancelar esta simulação?")), "dialogTitle"))
        self.values: list[QLabel] = []
        for block in rows:
            form = QFormLayout()
            for label, value in block:
                shown = QLabel(value)
                shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.values.append(shown)
                form.addRow(set_variant(QLabel(label), "dialogText"), shown)
            layout.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(set_variant(QLabel(_("Método:")), "dialogText"))
        self.method = QLabel(method)
        font = self.method.font()
        font.setBold(True)
        self.method.setFont(font)
        row.addWidget(self.method, 1)
        layout.addLayout(row)
        self.note = set_variant(QLabel(note), "dialogText")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        command = _("Comando que vai rodar no cluster:")
        layout.addWidget(set_variant(QLabel(command), "dialogText"))
        self.command = set_variant(QLabel(line), "mono")
        self.command.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.command)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = QPushButton(_("Voltar"))
        self.cancel_button = set_variant(QPushButton(_("Cancelar simulação")), "danger")
        self.back_button.clicked.connect(self.reject)
        self.cancel_button.clicked.connect(self.accept)
        self.cancel_button.setAutoDefault(False)  # focused, it would take Enter
        self.back_button.setDefault(True)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.back_button.setFocus()


def ask_cancel(
    parent: QWidget,
    rows: Sequence[Sequence[tuple[str, str]]],
    method: str,
    note: str,
    line: str,
) -> bool:
    """True when the user confirmed the cancellation."""
    dialog = CancelDialog(rows, method, note, line, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted
