""" "Submeter…" on a ``.qsub`` of the cluster mode (spec 69 R4): the menu item, the folder check, the
confirmation and what the answer tells the user, the LED and the queue.

The item is added through ``RemoteController.menu_hooks``: the cluster mode knows nothing of jobs.
What talks to the cluster (``core/remote/submit.py``) runs in a pool of one thread of its own, one
action at a time (a second click waits: the item is disabled with the reason). The folder is listed
and the queue asked when the item is clicked, and both again right before ``qsub``, after the
confirmation: a job of the user running in the folder blocks the submission, with a toast and no
dialog. The configuration is read when the user acts (``window.config``), so a reloaded
``config.yaml`` needs no wiring here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Hashable
from pathlib import PurePosixPath

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QMenu, QWidget

from ..core.config import AppConfig
from ..core.remote.actions import ActionFailure
from ..core.remote.submit import (
    SubmitBlocked,
    SubmitPlan,
    Submitted,
    plan_submit,
    submit,
    submit_steps,
)
from ..core.tasks import TaskGroup
from ..i18n import _
from .busy import BusyTracker
from .dialogs.cluster_action import ask_submit
from .jobs_controller import JobsController
from .remote_controller import RemoteController
from .sync_coordinator import SyncCoordinator
from .widgets.remote_model import RemotePath
from .widgets.toast import Toast
from .widgets.workspace_tabs import add_action

log = logging.getLogger(__name__)

KEY = "action"
BUSY_KEY = "cluster:action"
SCRIPT_SUFFIX = ".qsub"
CHECKING = _("Conferindo a pasta no cluster…")
SUBMITTING = _("Submetendo no cluster…")
WAIT = _("Aguarde: uma ação no cluster está em andamento.")
NO_SUBMIT = _("Submissão desligada: cluster.submit_command está vazio no config.yaml.")
NO_QUEUE = _(
    "Submeter precisa de cluster.jobs_command: é o qstatus que diz se já roda um job nesta pasta."
)


class JobActionsController(QObject):
    done = pyqtSignal(object)  # the end of an action: its answer, or None (declined); tests wait
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms)

    def __init__(
        self,
        remote: RemoteController,
        jobs: JobsController,
        sync: SyncCoordinator,
        busy: BusyTracker,
        toast: Toast,
        config: Callable[[], AppConfig],
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.remote, self.jobs, self.sync, self.busy, self.toast = remote, jobs, sync, busy, toast
        self._config, self._dialog_parent = config, dialog_parent
        self._pending: tuple[AppConfig, str | None] | None = None  # the action's config, password
        self._plan: SubmitPlan | None = None  # the confirmed one, while it is submitted
        self._pool = QThreadPool()  # no Qt parent (CLAUDE.md, Threading)
        self._pool.setMaxThreadCount(1)
        self._tasks = TaskGroup(self._pool)

    @classmethod
    def for_window(cls, window) -> JobActionsController:
        controller = cls(
            window.remote,
            window.jobs,
            window.sync,
            window.plot_workflow.busy,
            window.toast,
            lambda: window.config,
            window,
            parent=window,
        )
        window.remote.menu_hooks.append(controller.add_to_menu)
        controller.message.connect(window.status.set_message)
        return controller

    @property
    def busy_now(self) -> bool:
        return self._tasks.active(KEY) is not None

    def cancel(self) -> None:
        """Window close (the "cancelar" step): a running check or ``qsub`` has its ssh killed
        within ``core/sync/command.py:POLL_SECONDS``. A ``qsub`` that reached the cluster may have
        submitted: the next session's queue shows it."""
        self._tasks.shutdown(0)
        self._pending = self._plan = None
        self.busy.end(BUSY_KEY)

    # -- the menu --------------------------------------------------------------------------------
    def add_to_menu(self, menu: QMenu, items: list[RemotePath]) -> None:
        """ "Submeter…" for one ``.qsub`` file; disabled with the reason when it cannot run."""
        if len(items) != 1 or items[0].is_dir or not items[0].path.endswith(SCRIPT_SUFFIX):
            return
        item = items[0]
        reason = self.submit_blocked(item)
        add_action(
            menu,
            _("Submeter…"),
            lambda: self.start_submit(item),
            enabled=not reason,
            tooltip=reason,
        )

    def submit_blocked(self, item: RemotePath) -> str:
        """Why ``item`` cannot be submitted now; "" when it can."""
        config = self._config()
        if not config.cluster.submit_command:
            return NO_SUBMIT
        if not config.cluster.jobs_command:
            return NO_QUEUE
        path = PurePosixPath(item.path)
        try:
            submit_steps(config, str(path.parent), path.name)
        except ValueError as exc:
            return str(exc)
        return WAIT if self.busy_now else ""

    # -- submitting ------------------------------------------------------------------------------
    def start_submit(self, item: RemotePath) -> None:
        """Check the folder on the cluster; the confirmation follows when nothing blocks it."""
        if self.submit_blocked(item):
            return
        config = self._config()
        cluster = config.cluster
        needs_password = cluster.auth == "password" and cluster.resolve_password() is None
        password = None
        if needs_password:
            password = self.sync.session_password(ask=True)
            if password is None:
                return
        path = PurePosixPath(item.path)
        self._pending = (config, password)
        self._tasks.submit(
            KEY,
            plan_submit,
            config,
            str(path.parent),
            path.name,
            password,
            on_done=self._on_planned,
            on_error=self._on_error,
        )
        self.busy.begin(BUSY_KEY, CHECKING)

    def _on_planned(
        self, _key: Hashable, result: SubmitPlan | SubmitBlocked | ActionFailure
    ) -> None:
        self.busy.end(BUSY_KEY)
        pending = self._pending
        if pending is None:
            return
        if not isinstance(result, SubmitPlan):
            self._pending = None
            self._tell(result)
            self.done.emit(result)
            return
        config, password = pending
        account = f"{config.cluster.user}@{config.cluster.host}"
        if not ask_submit(self._dialog_parent, result, account):
            self._pending = None
            self.done.emit(None)
            return
        self._plan = result
        self._tasks.submit(
            KEY,
            submit,
            config,
            result,
            password,
            on_done=self._on_submitted,
            on_error=self._on_error,
        )
        self.busy.begin(BUSY_KEY, SUBMITTING)

    def _on_submitted(
        self, _key: Hashable, result: Submitted | str | SubmitBlocked | ActionFailure
    ) -> None:
        self.busy.end(BUSY_KEY)
        plan, self._pending, self._plan = self._plan, None, None
        self._tell(result)
        if plan is not None and isinstance(result, Submitted | str):  # qsub ended with code 0
            self.jobs.refresh()  # the new job shows in the queue
            self._list_again(plan.remote_dir)
        self.done.emit(result)

    def _on_error(self, key: Hashable, error: Exception) -> None:
        log.error("cluster action failed", exc_info=error)
        message = _("Falha na ação no cluster: {error}").format(error=error)
        self._on_submitted(key, ActionFailure(message, local=True))

    def _tell(self, result: Submitted | str | SubmitBlocked | ActionFailure) -> None:
        """The toast (and the footer, for a job), and what the answer tells the LED: as the jobs'
        and the listings' answers, a refused login forgets the password."""
        monitor = self.sync.monitor
        if isinstance(result, ActionFailure):
            text = _("A submissão falhou: {message}").format(message=result.message)
            self.toast.show_message(text, "error")
            if result.connection:
                monitor.report(False)
            elif not (result.auth or result.local):
                monitor.report(True)  # the cluster answered: it is the command that failed
            if result.auth:
                self.sync.forget_password()
            return
        monitor.report(True)
        if isinstance(result, Submitted):
            text = _("Job {job_id} ({name}) submetido.").format(
                job_id=result.job_id, name=result.name
            )
            self.toast.show_message(text, "info")
            self.message.emit(text, "info", 10000)
        elif isinstance(result, SubmitBlocked):
            self.toast.show_message(result.message, "warning")
        else:
            text = _("O qsub terminou sem erro, mas a resposta não foi reconhecida: {line}")
            self.toast.show_message(text.format(line=result), "warning")

    def _list_again(self, remote_dir: str) -> None:
        """The folder of the new job: listed again when the cluster mode shows it, else out of the
        cache (its ``.o`` file comes when the job starts)."""
        remote = self.remote
        if remote.active and remote.current == remote_dir:
            remote.refresh()
        elif remote.browser is not None:
            remote.browser.invalidate(remote_dir)
