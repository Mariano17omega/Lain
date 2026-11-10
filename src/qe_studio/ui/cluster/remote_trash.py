""" "Apagar…" in the cluster mode (spec 84 R2): the menu item, the check, the confirmation and what the
answer tells the user. Nothing is deleted: the items move into ``<remote_root>/trash/``.

The item is added through ``RemoteController.menu_hooks`` after "Submeter…" and "Cancelar simulação…",
for files and folders of one folder, and is disabled with the reason when they cannot go (the root,
the trash itself or what is in it, a name unfit for a command), without ``cluster.jobs_command``,
during a sync and while another action on the cluster runs; no sync starts from the click to the end
of the move (``sync_blocked``, one of the coordinator's ``guards``), since rsync would find the folder
gone halfway. ``core/remote/trash.py`` lists the folder
and asks the queue when the item is clicked and again right before ``mv``; the dialog shows each item
and its target and the exact commands, "Cancelar" by default. The pool, the password, the LED and the
listing again are ``ui/cluster/job_actions.py``'s: one action on the cluster at a time, and none after
the window closes (its ``cancel``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMenu, QWidget

from ...core.config import AppConfig
from ...core.remote.failure import RemoteFailure
from ...core.remote.trash import (
    Move,
    TrashBlocked,
    TrashDone,
    TrashPlan,
    plan_trash,
    run_trash,
    trash_blocked,
)
from ...core.remote.trash_dir import trash_of
from ...core.sync.request import SYNC_RUNNING
from ...i18n import _, ngettext
from ..dialogs.cluster_action import ask_trash
from ..widgets.cluster.remote_model import RemotePath
from ..widgets.shell.workspace_tabs import add_action
from ..widgets.toast import Toast
from .job_actions import WAIT, JobActionsController
from .remote_controller import RemoteController
from .sync_coordinator import SyncCoordinator

DELETE = _("Apagar…")
CHECKING = _("Conferindo no cluster…")
MOVING = _("Movendo para trash…")
NO_QUEUE = _(
    "Apagar precisa de cluster.jobs_command: é o qstatus que diz se roda um job nesta pasta."
)


class RemoteTrashController(QObject):
    done = pyqtSignal(object)  # the end of an "Apagar…": its answer, or None (declined); tests wait

    def __init__(
        self,
        actions: JobActionsController,
        remote: RemoteController,
        sync: SyncCoordinator,
        toast: Toast,
        config: Callable[[], AppConfig],
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.actions, self.remote, self.sync, self.toast = actions, remote, sync, toast
        self._config, self._dialog_parent = config, dialog_parent
        self._pending: tuple[AppConfig, str | None] | None = None  # the action's config, password
        self._plan: TrashPlan | None = None  # the confirmed one, while it moves

    @classmethod
    def for_window(cls, window) -> RemoteTrashController:
        controller = cls(
            window.job_actions,
            window.remote,
            window.sync,
            window.toast,
            lambda: window.config,
            window,
            parent=window,
        )
        window.remote.menu_hooks.append(controller.add_to_menu)
        window.sync.guards.append(controller.sync_blocked)
        return controller

    def sync_blocked(self) -> str:
        """Why a pull or a push cannot start now: items are being checked or moved."""
        return WAIT if self._pending is not None or self._plan is not None else ""

    # -- the menu --------------------------------------------------------------------------------
    def add_to_menu(self, menu: QMenu, items: list[RemotePath]) -> None:
        """ "Apagar…" for the items; disabled with the reason when they cannot go now."""
        reason = self.blocked(items)
        add_action(menu, DELETE, lambda: self.start(items), enabled=not reason, tooltip=reason)

    def blocked(self, items: list[RemotePath]) -> str:
        """Why ``items`` cannot go to the trash now; "" when they can."""
        config = self._config()
        if reason := trash_blocked(config, items):
            return reason
        if not config.cluster.jobs_command:
            return NO_QUEUE
        if self.sync.running:
            return SYNC_RUNNING
        return WAIT if self.actions.busy_now else ""

    # -- moving ----------------------------------------------------------------------------------
    def start(self, items: list[RemotePath]) -> None:
        """Check on the cluster; the confirmation follows when nothing blocks it."""
        if self.blocked(items):
            return
        config = self._config()
        go_on, password = self.actions.password(config)
        if not go_on:
            return
        self._pending = (config, password)
        plain = [(item.path, item.is_dir) for item in items]
        self.actions.run(CHECKING, plan_trash, config, plain, password, on_done=self._on_planned)

    def _on_planned(self, result: TrashPlan | TrashBlocked | RemoteFailure) -> None:
        pending, self._pending = self._pending, None
        if pending is None:
            return
        if not isinstance(result, TrashPlan):
            self._tell(result)
            self.done.emit(result)
            return
        self.actions.report(None)
        config, password = pending
        account = config.cluster.account
        if not ask_trash(self._dialog_parent, result, account):
            self.done.emit(None)
            return
        self._plan = result
        self.actions.run(MOVING, run_trash, config, result, password, on_done=self._on_moved)

    def _on_moved(self, result: TrashDone | TrashBlocked | RemoteFailure) -> None:
        plan, self._plan = self._plan, None
        self._tell(result)
        reached = not isinstance(result, RemoteFailure) or result.answered
        if plan is not None and reached:
            moved = result.moved if isinstance(result, TrashDone) else ()
            self._list_again(plan, moved)
        self.done.emit(result)

    def _list_again(self, plan: TrashPlan, moved: tuple[Move, ...]) -> None:
        """The folder of the items listed again, the trash's folders out of the cache; the folder
        above when the one shown went to the trash (deleted from the tree). ``moved``: what really
        left its folder, which is less than the plan when a step stopped the others."""
        remote, root = self.remote, self._config().paths.remote_root
        browser = remote.browser
        if browser is not None:
            browser.invalidate(plan.remote_dir)
            for _item, target in moved:
                folder = PurePosixPath(root, target).parent
                while folder.is_relative_to(trash_of(root)):
                    browser.invalidate(str(folder))
                    folder = folder.parent
        sources = [PurePosixPath(root, item) for item, _target in moved]
        if remote.active and any(PurePosixPath(remote.current).is_relative_to(s) for s in sources):
            remote.open(plan.remote_dir)
        else:
            self.actions.list_again(plan.remote_dir)

    def _tell(self, result: TrashDone | TrashBlocked | RemoteFailure) -> None:
        """The toast, and what the answer tells the LED."""
        if isinstance(result, RemoteFailure):
            text = _("Nada foi movido para trash: {message}").format(message=result.message)
            self.toast.show_message(text, "error")
            self.actions.report(result)
            return
        self.actions.report(result.failure if isinstance(result, TrashDone) else None)
        if isinstance(result, TrashBlocked):
            self.toast.show_message(result.message, "warning")
            return
        count = len(result.moved)
        text = ngettext("{n} item movido para trash", "{n} itens movidos para trash", count)
        details = "\n".join(f"{item} → {target}" for item, target in result.moved)
        if result.failure is None:
            self.toast.show_message(text.format(n=count), "info", details)
            return
        stopped = _("{moved}; o resto parou: {message}").format(
            moved=text.format(n=count), message=result.failure.message
        )
        self.toast.show_message(stopped, "warning", details)
