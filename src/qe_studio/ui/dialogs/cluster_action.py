"""Confirmations before a command that changes the cluster (spec 69 R4.4, spec 70 R6, spec 71 R3,
spec 84 R2.2): what runs, where, exactly, and a job of the same name already on the cluster."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.remote.cluster_jobs import Job
from ...core.remote.submit import SubmitPlan
from ...core.remote.trash import TrashPlan
from ...i18n import _
from ..theme.scale import scaled
from ..widgets.common import set_variant

log = logging.getLogger(__name__)

MAX_LINES = 10  # a longer list scrolls: the buttons stay on screen
LINE_PX = 16  # a line of ``#detailsText`` (11 px mono) at scale 1
BOX_PADDING_PX = 22  # the frame, the margins and a horizontal scroll bar


def _text_box(lines: Sequence[str]) -> QPlainTextEdit:
    """``lines`` to read and select, no wrapping, as tall as up to ``MAX_LINES`` of them. A remote
    path or command has no length limit: it scrolls instead of stretching the window."""
    box = QPlainTextEdit("\n".join(lines))
    box.setObjectName("detailsText")
    box.setReadOnly(True)
    box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    box.setFixedHeight(scaled(LINE_PX * min(len(lines), MAX_LINES) + BOX_PADDING_PX))
    return box


def _folder_label(account: str, folder: str) -> QLabel:
    """ "Pasta: conta:/caminho", wrapped: a long path must not make the window wider than the
    screen."""
    label = set_variant(
        QLabel(_("Pasta: {account}:{folder}").format(account=account, folder=folder)), "dialogText"
    )
    label.setWordWrap(True)
    return label


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
        layout.addWidget(_folder_label(account, plan.remote_dir))
        if plan.job_name:
            job = _("Job: {name}").format(name=plan.job_name)
            layout.addWidget(set_variant(QLabel(job), "dialogText"))
        layout.addWidget(set_variant(QLabel(_("Comandos que vão rodar no cluster:")), "dialogText"))
        self.commands = _text_box(plan.steps)
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
    log.info("confirm: submit accepted=%s", accepted)
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
    log.info("confirm: same_name accepted=%s", accepted)
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
                shown.setWordWrap(True)
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
        self.command = _text_box(line.splitlines() or [line])
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
    log.info("confirm: cancel accepted=%s", accepted)
    return accepted


TRASH_NOTE = _(
    "Os itens vão para a pasta trash na raiz do cluster. O Lain nunca apaga de vez: para isso, entre "
    "em trash pelo terminal."
)


class TrashDialog(QDialog):
    """ "Mover para trash?": each item and where it goes, what the trash is and the exact commands.
    "Cancelar" is the default: Enter moves nothing."""

    def __init__(self, plan: TrashPlan, account: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_("Apagar no cluster"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel(_("Mover para trash?")), "dialogTitle"))
        layout.addWidget(_folder_label(account, plan.remote_dir))
        self.moves = _text_box([f"{item} → {target}" for item, target in plan.moves])
        layout.addWidget(self.moves)
        self.note = set_variant(QLabel(TRASH_NOTE), "dialogText")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addWidget(set_variant(QLabel(_("Comandos que vão rodar no cluster:")), "dialogText"))
        self.commands = _text_box(plan.steps)
        layout.addWidget(self.commands)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton(_("Cancelar"))
        self.move_button = set_variant(QPushButton(_("Mover para trash")), "danger")
        self.cancel_button.clicked.connect(self.reject)
        self.move_button.clicked.connect(self.accept)
        self.move_button.setAutoDefault(False)  # focused, it would take Enter
        self.cancel_button.setDefault(True)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.move_button)
        layout.addLayout(buttons)
        self.cancel_button.setFocus()


def ask_trash(parent: QWidget, plan: TrashPlan, account: str) -> bool:
    """True when the user confirmed the move to the trash."""
    dialog = TrashDialog(plan, account, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    log.info("confirm: trash accepted=%s", accepted)
    return accepted
