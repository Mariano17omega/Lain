""" "Cancelar simulação…" in the cluster mode and the cancel buttons of the queue popup (spec 70 R4–R5).

The method is never chosen, it follows where the user clicked: a folder (or a ``.qsub``, its folder)
stops the user's job running there with ``<prefix>.EXIT``, one per prefix of its SCF, relax and
vc-relax inputs (spec 71 R2); a button of the popup deletes a job still waiting with ``qdel``. That
button is disabled only when ``cluster.delete_command`` is empty: an action in progress is checked
when it is clicked, with a toast (spec 71 R6). ``core/remote/job_cancel.py`` checks a fresh queue before the dialog and
again right before acting; the dialog shows the job, the method and the exact command, "Voltar" by
default. The pool, the password, the LED and the listing again are ``ui/job_actions.py``'s: one
action on the cluster at a time, submitting included.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMenu, QWidget

from ..core.cluster_jobs import Job
from ..core.config import AppConfig
from ..core.remote.actions import ActionFailure, checked_dir
from ..core.remote.job_cancel import (
    Done,
    NotRunning,
    Refused,
    StopPlan,
    delete_line,
    delete_waiting,
    plan_stop,
    stop,
)
from ..i18n import _
from .dialogs.cluster_action import ask_cancel
from .job_actions import SCRIPT_SUFFIX, WAIT, JobActionsController
from .jobs_controller import JobsController
from .remote_controller import RemoteController
from .widgets.remote_model import RemotePath
from .widgets.toast import Toast
from .widgets.workspace_tabs import add_action

CANCEL = _("Cancelar simulação…")
CHECKING = _("Conferindo o job no cluster…")
STOPPING = _("Criando o arquivo de parada…")
DELETING = _("Cancelando o job na fila…")
NO_QUEUE = _(
    "Cancelar precisa de cluster.jobs_command: é o qstatus que diz se a simulação está rodando."
)
NO_DELETE = _("Cancelamento da fila desligado: cluster.delete_command está vazio no config.yaml.")
NOTE_EXIT = _(
    "Um arquivo por prefix dos inputs de scf, relax e vc-relax da pasta. O pw.x procura o seu "
    'durante a execução, para de forma limpa ("Program stopped by user request") e o apaga. Um '
    "pw.x seguinte do script com o mesmo prefix (nscf, bands) ainda roda, a partir do cálculo "
    "interrompido; com outro prefix desta lista, para logo na primeira verificação. Os demais "
    "programas (bands.x, projwfc.x…) ainda rodam. Se nenhum pw.x estiver rodando agora, o arquivo "
    "fica na pasta e a próxima submissão avisa."
)
NOTE_QDEL = _("Antes do qdel o Lain consulta a fila de novo: se o job já começou, nada é feito.")

Rows = list[list[tuple[str, str]]]


class JobCancelController(QObject):
    done = pyqtSignal(object)  # the end of a cancellation: its answer, or None (declined)

    def __init__(
        self,
        actions: JobActionsController,
        jobs: JobsController,
        remote: RemoteController,
        toast: Toast,
        config: Callable[[], AppConfig],
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.actions, self.jobs, self.remote, self.toast = actions, jobs, remote, toast
        self._config, self._dialog_parent = config, dialog_parent
        self._pending: tuple[AppConfig, str | None] | None = None  # the action's config, password
        self._folder: str | None = None  # the folder whose stop file is being created

    @classmethod
    def for_window(cls, window) -> JobCancelController:
        controller = cls(
            window.job_actions,
            window.jobs,
            window.remote,
            window.toast,
            lambda: window.config,
            window,
            parent=window,
        )
        window.remote.menu_hooks.append(controller.add_to_menu)
        popup = window.jobs.popup
        popup.cancel_requested.connect(controller.cancel_waiting)
        popup.cancel_reason = controller.waiting_blocked
        return controller

    def _account(self, config: AppConfig) -> str:
        return f"{config.cluster.user}@{config.cluster.host}"

    # -- a running job: the menu of a folder -----------------------------------------------------
    def add_to_menu(self, menu: QMenu, items: list[RemotePath]) -> None:
        """ "Cancelar simulação…" for one folder or one ``.qsub`` (its folder)."""
        if len(items) != 1:
            return
        item = items[0]
        if item.is_dir:
            folder = item.path
        elif item.path.endswith(SCRIPT_SUFFIX):
            folder = str(PurePosixPath(item.path).parent)
        else:
            return
        reason = self.stop_blocked(folder)
        add_action(
            menu, CANCEL, lambda: self.start_stop(folder), enabled=not reason, tooltip=reason
        )

    def stop_blocked(self, folder: str) -> str:
        """Why a job running in ``folder`` cannot be cancelled now; "" when it can."""
        config = self._config()
        if not config.cluster.jobs_command:
            return NO_QUEUE
        try:
            checked_dir(config, folder)
        except ValueError as exc:
            return str(exc)
        return WAIT if self.actions.busy_now else ""

    def start_stop(self, folder: str) -> None:
        """Check on the cluster that a job of the user runs in ``folder``; the dialog follows."""
        if self.stop_blocked(folder):
            return
        config = self._config()
        go_on, password = self.actions.password(config)
        if not go_on:
            return
        self._pending = (config, password)
        self.actions.run(
            CHECKING, plan_stop, config, folder, password, on_done=self._on_stop_planned
        )

    def _on_stop_planned(self, result: StopPlan | NotRunning | ActionFailure) -> None:
        pending, self._pending = self._pending, None
        if pending is None:
            return
        if not isinstance(result, StopPlan):
            self._tell(result)
            self.done.emit(result)
            return
        self.actions.report(None)
        config, password = pending
        account, folder = self._account(config), result.remote_dir
        rows: Rows = [
            [
                (_("Job"), job.name),
                (_("ID"), job.job_id),
                (_("Dono"), job.owner or ""),
                (_("Início"), job.date),
                (_("Núcleos"), str(job.slots)),
                (_("Pasta"), f"{account}:{folder}"),
            ]
            for job in result.jobs
        ]
        files = ", ".join(
            f"{source.prefix}.EXIT ({', '.join(source.inputs)})" for source in result.sources
        )
        method = _("arquivo de parada do pw.x: {files}").format(files=files)
        if not ask_cancel(self._dialog_parent, rows, method, NOTE_EXIT, result.line):
            self.done.emit(None)
            return
        self._folder = folder
        self.actions.run(STOPPING, stop, config, result, password, on_done=self._on_answer)

    # -- a waiting job: the button of the queue popup --------------------------------------------
    def waiting_blocked(self, _job: Job) -> str:
        """Why the button of a waiting job is disabled; "" when it is not (the popup asks per row).
        An action in progress is not a reason here: it may end while the popup is open."""
        return "" if self._config().cluster.delete_command else NO_DELETE

    def cancel_waiting(self, job: Job) -> None:
        """The popup closes first; then the dialog, and ``qdel`` once confirmed and checked. What
        keeps it from running now is a toast, never silence."""
        self.jobs.popup.hide()
        reason = self.waiting_blocked(job) or (WAIT if self.actions.busy_now else "")
        if reason:
            self.toast.show_message(reason, "warning")
            return
        config = self._config()
        try:
            line = delete_line(config, job)
        except ValueError as exc:
            failure = ActionFailure(str(exc), local=True)
            self._tell(failure)
            self.done.emit(failure)
            return
        go_on, password = self.actions.password(config)
        if not go_on:
            return
        rows: Rows = [
            [
                (_("Job"), job.name),
                (_("ID"), job.job_id),
                (_("Dono"), job.owner or ""),
                (_("Envio"), job.date),
                (_("Núcleos"), str(job.slots)),
                (_("Pasta"), _("não informada pelo qstatus")),
            ]
        ]
        method = _("qdel {job_id} (o job sai da fila antes de começar)").format(job_id=job.job_id)
        if not ask_cancel(self._dialog_parent, rows, method, NOTE_QDEL, line):
            self.done.emit(None)
            return
        self._folder = None
        self.actions.run(DELETING, delete_waiting, config, job, password, on_done=self._on_answer)

    # -- the answer ------------------------------------------------------------------------------
    def _on_answer(self, result: Done | Refused | ActionFailure) -> None:
        folder, self._folder = self._folder, None
        self._tell(result)
        reached = not isinstance(result, ActionFailure) or not (
            result.connection or result.auth or result.local
        )
        if reached:
            self.jobs.refresh()  # the job leaves the queue, now or at pw.x's next check
            if folder is not None:
                self.actions.list_again(folder)  # the new <prefix>.EXIT
        self.done.emit(result)

    def _tell(self, result: Done | Refused | NotRunning | ActionFailure) -> None:
        """The toast, and what the answer tells the LED."""
        if isinstance(result, ActionFailure):
            text = _("O cancelamento falhou: {message}").format(message=result.message)
            self.toast.show_message(text, "error")
            self.actions.report(result)
            return
        self.actions.report(None)
        level = "warning" if isinstance(result, Refused) else "info"
        self.toast.show_message(result.message, level)
