"""Cluster pull from the window (PRD §5): password of the session, conflict prompts, final report,
and the cluster label of the reachability monitor.

``core/sync`` decides (``prepare_sync``) and runs (``SyncController``); this only asks, shows and
reports. The window refreshes what changed when ``synced`` arrives.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from ..core.config import AppConfig
from ..core.sync.controller import SyncController, SyncReport, SyncStatus
from ..core.sync.monitor import ConnectionMonitor
from ..core.sync.planner import PlanItem
from ..core.sync.request import SyncRefusal, prepare_sync
from ..core.sync.rsync import Endpoint
from .dialogs.sync_dialog import ConflictDialog, SyncDialog
from .theme.manager import ThemeManager

TITLE = "Sincronização"


class SyncCoordinator(QObject):
    finished = pyqtSignal(object)  # SyncReport, after its message was shown
    synced = pyqtSignal(object)  # Path: the local folder a sync may have changed
    cluster_changed = pyqtSignal(str, str)  # label (user@host), monitor state
    message = pyqtSignal(str, str, int)  # status bar: text, level, timeout (ms)

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
        self.controller: SyncController | None = None
        self.dialog: SyncDialog | None = None
        self.conflict_dialog: ConflictDialog | None = None
        self._session_password: str | None = None  # typed once per run, never saved
        self.monitor = self._new_monitor()

    @property
    def running(self) -> bool:
        return self.controller is not None and self.controller.running

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

    # -- a pull -----------------------------------------------------------------------------------
    def start(self, folder: Path) -> None:
        """Pull ``folder`` from the cluster (the whole project when it is the root)."""
        if self.running:
            return
        request = prepare_sync(self.config, folder)
        if isinstance(request, SyncRefusal):
            show = QMessageBox.information if request.level == "info" else QMessageBox.warning
            show(self._dialog_parent, TITLE, request.message)
            return
        password = None
        if request.needs_password:
            password = self._ask_password()
            if password is None:
                return
        self.run(request.folder, request.endpoint, password)

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
        dialog = SyncDialog(
            self.theme, controller, endpoint.spec(), str(folder), self._dialog_parent
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        controller.conflict_needed.connect(self._ask_conflict)
        controller.finished.connect(self._on_finished)
        self.controller, self.dialog = controller, dialog
        self.monitor.set_syncing(True)
        dialog.open()
        controller.start(folder, endpoint)

    def _ask_conflict(self, item: PlanItem) -> None:
        assert self.controller is not None
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
        controller, self.controller, self.dialog = self.controller, None, None
        if controller is not None:
            controller.deleteLater()
        self.monitor.set_syncing(False)
        if report.status is not SyncStatus.CANCELLED:
            self.monitor.report(not report.connection_failed)
        if report.status is SyncStatus.FAILED and "Autenticação" in (report.error or ""):
            self._session_password = None
        self.synced.emit(report.local_dir)
        parent = self._dialog_parent
        if report.status is SyncStatus.FAILED:
            QMessageBox.critical(parent, TITLE, report.message)
        elif report.status is SyncStatus.LOCAL_NEWER:
            QMessageBox.warning(parent, TITLE, report.message)
        elif report.status is SyncStatus.CANCELLED:
            self.message.emit(report.message, "warning", 5000)
        else:
            QMessageBox.information(parent, TITLE, report.message)
            self.message.emit(report.message.splitlines()[0], "info", 6000)
        self.finished.emit(report)
