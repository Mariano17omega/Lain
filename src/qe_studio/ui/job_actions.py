""" "Submeter…" on a ``.qsub`` of the cluster mode (spec 69 R4): the menu item, the folder check, the
confirmation and what the answer tells the user, the LED and the queue.

The item is added through ``RemoteController.menu_hooks``: the cluster mode knows nothing of jobs.
What talks to the cluster (``core/remote/submit.py``) runs in a pool of one thread of its own, one
action at a time (a second click waits: the item is disabled with the reason). The folder is listed
and the queue asked when the item is clicked, and both again right before ``qsub``, after the
confirmation: a job of the user running in the folder, or one Lain submitted from it still in the
queue, blocks the submission, with a toast and no dialog. A job of the user with the script's name
asks first (spec 71 R3). The configuration is read when the user acts (``window.config``), so a reloaded
``config.yaml`` needs no wiring here.

Cancelling a job (spec 70, ``ui/job_cancel.py``) shares the pool through ``password``, ``run``,
``report`` and ``list_again``: one action on the cluster at a time, whichever it is.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Hashable
from pathlib import PurePosixPath
from typing import Any

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
from .dialogs.cluster_action import ask_same_name, ask_submit
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
        self._then: Callable[[Any], None] | None = None  # who gets the answer of the running action
        self._closed = False  # the window is closing: nothing new reaches the cluster (spec 71 R5)
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
        submitted: the next session's queue shows it. No action starts afterwards, not even one a
        dialog still open confirms."""
        self._closed = True
        self._tasks.shutdown(0)
        self._pending = self._plan = self._then = None
        self.busy.end(BUSY_KEY)

    # -- what every cluster action shares --------------------------------------------------------
    def password(self, config: AppConfig) -> tuple[bool, str | None]:
        """(go on, the password typed in this session): the sync's dialog asks for it once when
        ``auth: password`` finds none in the config or the environment; (False, None) when the user
        cancelled it."""
        cluster = config.cluster
        if cluster.auth != "password" or cluster.resolve_password() is not None:
            return True, None
        password = self.sync.session_password(ask=True)
        return password is not None, password

    def run(self, label: str, fn: Callable, *args: Any, on_done: Callable[[Any], None]) -> None:
        """``fn(*args)`` in the pool of the cluster actions, with ``label`` in the footer;
        ``on_done(answer)`` on the GUI thread, an exception as an ``ActionFailure``. Never after
        ``cancel()``, which also refuses new actions. One action at a time: callers check
        ``busy_now`` first."""
        if self._closed:
            return
        self._then = on_done
        self._tasks.submit(KEY, fn, *args, on_done=self._on_done, on_error=self._on_error)
        self.busy.begin(BUSY_KEY, label)

    def _on_done(self, _key: Hashable, result: object) -> None:
        self.busy.end(BUSY_KEY)
        then, self._then = self._then, None
        if then is not None:
            then(result)

    def _on_error(self, key: Hashable, error: Exception) -> None:
        log.error("cluster action failed", exc_info=error)
        message = _("Falha na ação no cluster: {error}").format(error=error)
        self._on_done(key, ActionFailure(message, local=True))

    def report(self, failure: ActionFailure | None) -> None:
        """What an answer tells the LED, as the jobs' and the listings' answers do (None: the
        cluster answered); a refused login forgets the password."""
        monitor = self.sync.monitor
        if failure is None:
            monitor.report(True)
            return
        if failure.connection:
            monitor.report(False)
        elif not (failure.auth or failure.local):
            monitor.report(True)  # the cluster answered: it is the command that failed
        if failure.auth:
            self.sync.forget_password()

    def list_again(self, remote_dir: str) -> None:
        """A folder an action changed: listed again when the cluster mode shows it, else out of the
        cache."""
        remote = self.remote
        if remote.active and remote.current == remote_dir:
            remote.refresh()
        elif remote.browser is not None:
            remote.browser.invalidate(remote_dir)

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
        go_on, password = self.password(config)
        if not go_on:
            return
        path = PurePosixPath(item.path)
        self._pending = (config, password)
        args = (config, str(path.parent), path.name, password)
        self.run(CHECKING, plan_submit, *args, on_done=self._on_planned)

    def _on_planned(self, result: SubmitPlan | SubmitBlocked | ActionFailure) -> None:
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
        parent = self._dialog_parent
        if result.same_name and not ask_same_name(parent, result.job_name, result.same_name):
            self._pending = None
            self.done.emit(None)
            return
        if not ask_submit(parent, result, account):
            self._pending = None
            self.done.emit(None)
            return
        self._plan = result
        self.run(SUBMITTING, submit, config, result, password, on_done=self._on_submitted)

    def _on_submitted(self, result: Submitted | str | SubmitBlocked | ActionFailure) -> None:
        plan, self._pending, self._plan = self._plan, None, None
        self._tell(result)
        if plan is not None and isinstance(result, Submitted | str):  # qsub ended with code 0
            self.jobs.refresh()  # the new job shows in the queue
            self.list_again(plan.remote_dir)  # its .o file comes when the job starts
        self.done.emit(result)

    def _tell(self, result: Submitted | str | SubmitBlocked | ActionFailure) -> None:
        """The toast (and the footer, for a job), and what the answer tells the LED."""
        if isinstance(result, ActionFailure):
            text = _("A submissão falhou: {message}").format(message=result.message)
            self.toast.show_message(text, "error")
            self.report(result)
            return
        self.report(None)
        if isinstance(result, Submitted):
            text = _("Job {job_id} ({name}) submetido.").format(
                job_id=result.job_id, name=result.name
            )
            self.message.emit(text, "info", 10000)
            if result.log_error:
                more = _("O registro de jobs submetidos não pôde ser gravado ({error}).")
                self.toast.show_message(f"{text} {more.format(error=result.log_error)}", "warning")
            else:
                self.toast.show_message(text, "info")
        elif isinstance(result, SubmitBlocked):
            self.toast.show_message(result.message, "warning")
        else:
            text = _("O qsub terminou sem erro, mas a resposta não foi reconhecida: {line}")
            self.toast.show_message(text.format(line=result), "warning")
