"""Cluster pull (PRD §5) and push of new files (spec 27) from the window: password of the session,
the sync window (preview and conflict prompts), final report, the scope shown by the Rsync button,
the "Cluster" menu and the context menu's "Enviar ao cluster" (spec 17), and the cluster label of
the reachability monitor.

``core/sync`` decides (``prepare_sync``, ``prepare_push``, ``sync_scope``) and runs
(``SyncController``, ``PushController``); this only asks, shows and reports. One run at a time,
either way. The window refreshes what changed when ``synced`` arrives (a push changes nothing
local, so it never emits it); a run that went well ends with a toast (``notice``), not a message
box.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from ..core.config import AppConfig
from ..core.sync._process import RsyncRun
from ..core.sync.controller import SyncController, SyncReport, SyncStatus
from ..core.sync.monitor import ConnectionMonitor
from ..core.sync.planner import PlanItem
from ..core.sync.push import PushController
from ..core.sync.request import (
    Direction,
    SyncRefusal,
    SyncRequest,
    SyncScope,
    prepare_push,
    prepare_sync,
    push_availability,
    sync_scope,
)
from ..core.sync.rsync import Endpoint
from .dialogs.sync_dialog import ConflictDialog, SyncDialog
from .theme.manager import ThemeManager
from .widgets.context_menu import ItemActions

TITLE = "Sincronização"
PUSH_TITLE = "Envio ao cluster"


class SyncCoordinator(QObject):
    finished = pyqtSignal(object)  # SyncReport, after its message was shown
    synced = pyqtSignal(object)  # Path: the local folder a sync may have changed
    cluster_changed = pyqtSignal(str, str)  # label (user@host), monitor state
    message = pyqtSignal(str, str, int)  # status bar: text, level, timeout (ms)
    notice = pyqtSignal(str, str, str)  # toast: text, level, details (the full report)
    scope_changed = pyqtSignal(str)  # tooltip of the Rsync button: what it would pull

    def __init__(
        self,
        config: AppConfig,
        theme: ThemeManager,
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.config, self.theme = config, theme
        self._dialog_parent = dialog_parent
        self.controller: RsyncRun | None = None
        self.dialog: SyncDialog | None = None
        self.scope: SyncScope | None = None  # of the run in progress
        self.conflict_dialog: ConflictDialog | None = None
        self._session_password: str | None = None  # typed once per run, never saved
        self._scope_folder: Path = config.paths.local_root
        self._folder_action: QAction | None = None
        self._project_action: QAction | None = None
        self._push_action: QAction | None = None
        self.monitor = self._new_monitor()

    @property
    def running(self) -> bool:
        return self.controller is not None and self.controller.running

    @property
    def folder(self) -> Path | None:
        """The local folder of the run in progress (the root for the whole project), None when idle."""
        if not self.running or self.scope is None:
            return None
        root = self.config.paths.local_root
        return root / self.scope.relative if self.scope.relative else root

    def _new_monitor(self) -> ConnectionMonitor:
        monitor = ConnectionMonitor(self.config.cluster, self.config.sync_enabled, self)
        monitor.state_changed.connect(self._on_state)
        return monitor

    def start_monitor(self) -> None:
        self._on_state(self.monitor.state.value)
        self.monitor.start()

    def set_config(self, config: AppConfig) -> None:
        """Config reload: a new monitor for the new cluster."""
        self.config = config
        old = self.monitor
        old.stop()
        old.state_changed.disconnect(self._on_state)
        old.deleteLater()
        self.monitor = self._new_monitor()
        self.start_monitor()
        self.show_scope(self._scope_folder)

    # -- scope (spec 17 R1) -----------------------------------------------------------------------
    def bind_actions(self, actions: dict[str, QAction]) -> None:
        """The menu's "Sincronizar <pasta>", "Sincronizar projeto inteiro" and "Enviar <pasta> ao
        cluster…" (``sync.start``, ``sync.project``, ``sync.push``), kept up to date."""
        self._folder_action = actions.get("sync.start")
        self._project_action = actions.get("sync.project")
        self._push_action = actions.get("sync.push")
        self.show_scope(self._scope_folder)

    def bind_menu(self, item_actions: ItemActions) -> None:
        """The context menu's "Enviar ao cluster" of a folder (spec 27 R4.4)."""
        item_actions.push_state = self.push_state
        item_actions.push_requested.connect(self.push)

    def push_state(self, path: Path) -> str | None:
        """The context menu's item for ``path``: None hides it (files), "" enables it, any other
        text is why it is disabled."""
        return push_availability(self.config, path) if path.is_dir() else None

    def show_scope(self, folder: Path) -> None:
        """Say what a pull would cover now that ``folder`` is the current one."""
        self._scope_folder = folder
        scope = sync_scope(self.config, folder)
        enabled = self.config.sync_enabled
        if self._folder_action is not None:
            self._folder_action.setText(scope.menu_text)
            self._folder_action.setToolTip(scope.tooltip)
            self._folder_action.setEnabled(enabled)
        if self._project_action is not None:
            whole = sync_scope(self.config, self.config.paths.local_root)
            self._project_action.setToolTip(whole.tooltip)
            self._project_action.setEnabled(enabled)
        if self._push_action is not None:
            push = sync_scope(self.config, folder, direction=Direction.PUSH)
            self._push_action.setText(push.menu_text)
            self._push_action.setToolTip(push.tooltip)
            self._push_action.setEnabled(push.available)
        self.scope_changed.emit(scope.tooltip)

    def check_connection(self) -> None:
        self.monitor.check()

    def shutdown(self) -> None:
        if self.controller is not None and self.controller.running:
            self.controller.shutdown()
        self.monitor.stop()

    def _on_state(self, state: str) -> None:
        cluster = self.config.cluster
        label = (
            f"{cluster.user}@{cluster.host}" if cluster.configured else "cluster não configurado"
        )
        self.cluster_changed.emit(label, state)

    # -- a pull or a push -------------------------------------------------------------------------
    def start(self, folder: Path) -> None:
        """Pull ``folder`` from the cluster (the whole project when it is the root)."""
        if self.running:
            return
        request = self._checked(prepare_sync(self.config, folder), TITLE)
        if request is not None:
            self.run(*request)

    def push(self, folder: Path) -> None:
        """Send the new files of ``folder`` to the cluster (spec 27): never the project root."""
        if self.running:
            return
        request = self._checked(prepare_push(self.config, folder), PUSH_TITLE)
        if request is not None:
            self.run_push(*request)

    def start_push(self) -> None:
        """ "Enviar <pasta> ao cluster…" of the "Cluster" menu: the current folder."""
        self.push(self._scope_folder)

    def _checked(
        self, request: SyncRequest | SyncRefusal, title: str
    ) -> tuple[Path, Endpoint, str | None] | None:
        """(folder, endpoint, password) of a run that may start, after explaining a refusal or
        asking for the password; None when it does not start."""
        if isinstance(request, SyncRefusal):
            show = QMessageBox.information if request.level == "info" else QMessageBox.warning
            show(self._dialog_parent, title, request.message)
            return None
        password = None
        if request.needs_password:
            password = self._ask_password()
            if password is None:
                return None
        return request.folder, request.endpoint, password

    def _ask_password(self) -> str | None:
        if self._session_password:
            return self._session_password
        cluster = self.config.cluster
        text, ok = QInputDialog.getText(
            self._dialog_parent,
            "Senha do cluster",
            f"Senha de {cluster.user}@{cluster.host} (não é salva):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not text:
            return None
        self._session_password = text
        return text

    def run(self, folder: Path, endpoint: Endpoint, password: str | None = None) -> None:
        controller = SyncController(self.config, self, password=password)
        dialog = self._open(controller, sync_scope(self.config, folder, endpoint))
        controller.conflict_needed.connect(dialog.await_decision)
        controller.conflict_needed.connect(self._ask_conflict)
        controller.start(folder, endpoint)

    def run_push(self, folder: Path, endpoint: Endpoint, password: str | None = None) -> None:
        controller = PushController(self.config, self, password=password)
        self._open(controller, sync_scope(self.config, folder, endpoint, Direction.PUSH))
        controller.start(folder, endpoint)

    def _open(self, controller: RsyncRun, scope: SyncScope) -> SyncDialog:
        dialog = SyncDialog(self.theme, controller, scope, self._dialog_parent)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        controller.finished.connect(self._on_finished)
        self.controller, self.dialog, self.scope = controller, dialog, scope
        self.monitor.set_syncing(True)
        dialog.open()
        return dialog

    def _ask_conflict(self, item: PlanItem) -> None:
        assert isinstance(self.controller, SyncController)
        dialog = ConflictDialog(item, self.dialog or self._dialog_parent)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.decided.connect(self.controller.resolve)
        dialog.finished.connect(self._on_conflict_closed)
        self.conflict_dialog = dialog
        dialog.open()

    def _on_conflict_closed(self, _result: int) -> None:
        self.conflict_dialog = None

    def _on_finished(self, report: SyncReport) -> None:
        # The dialog deletes itself on close; the controller goes on the next loop turn.
        controller, dialog, scope = self.controller, self.dialog, self.scope
        self.controller, self.dialog, self.scope = None, None, None
        if controller is not None:
            controller.deleteLater()
        self.monitor.set_syncing(False)
        if report.status is not SyncStatus.CANCELLED:
            self.monitor.report(not report.connection_failed)
        if report.status is SyncStatus.FAILED and "Autenticação" in (report.error or ""):
            self._session_password = None
        if report.changes_local:
            self.synced.emit(report.local_dir)
        # What needs attention opens over the sync window, which closes after it (spec 17 R2.3).
        parent = dialog or self._dialog_parent
        title = PUSH_TITLE if scope is not None and scope.push else TITLE
        if report.status is SyncStatus.FAILED:
            QMessageBox.critical(parent, title, report.message)
        elif report.status is SyncStatus.LOCAL_NEWER:
            QMessageBox.warning(parent, title, report.message)
        if dialog is not None:
            dialog.finish()
        if report.status is SyncStatus.CANCELLED:
            self.message.emit(report.message, "warning", 5000)
        elif report.status in (SyncStatus.DONE, SyncStatus.UP_TO_DATE):
            headline = report.headline
            self.message.emit(headline, "warning" if report.changed_locally else "info", 6000)
            level = "success" if report.status is SyncStatus.DONE else "info"
            if report.changed_locally:
                level = "warning"  # files were left out: the toast says so
            self.notice.emit(headline, level, report.details)
        self.finished.emit(report)
