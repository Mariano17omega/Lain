"""The jobs of the cluster on the top bar (spec 64 R4–R6): when to ask, what the indicator says, the
queue popup and what the answer tells the LED.

``cluster.jobs_command`` (``qstatus -a``) runs on the cluster when the window opens, then every
``cluster.jobs_poll_seconds`` while the window is active: each query logs in, so an inactive window
asks nothing, as with the reachability monitor. One query at a time, in a pool of its own (a hung ssh
never holds a thread of the global pool). The last answer is the cache of the session, in memory
only. A login the cluster refused, or a command it does not have, stops the automatic queries until
"Atualizar", "Tentar de novo" or "Recarregar config.yaml": a refused login repeated every few minutes
can get the address blocked on the cluster (``core/sync/monitor.py``). With ``auth: password`` and no
password known, nothing is asked on its own: a click on the indicator asks (spec 64 decision 6).

The answer feeds the LED: a query that reached the cluster is a real login, ``report(True)``; one that
did not, ``report(False)``. A refused login leaves it alone: the cluster did answer.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Hashable

from PyQt6.QtCore import QObject, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from ..core.cluster_jobs import Job, JobsFailure, JobsSnapshot, fetch_jobs
from ..core.config import AppConfig
from ..core.tasks import TaskGroup
from ..i18n import _
from .sync_coordinator import SyncCoordinator
from .widgets.jobs_indicator import JobsIndicator
from .widgets.jobs_popup import JobsPopup, clock

log = logging.getLogger(__name__)

KEY = "jobs"


class JobsController(QObject):
    fetched = pyqtSignal(object)  # JobsSnapshot | JobsFailure, after every answer

    def __init__(
        self,
        indicator: JobsIndicator,
        popup: JobsPopup,
        sync: SyncCoordinator,
        config: AppConfig,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.indicator, self.popup, self.sync, self.config = indicator, popup, sync, config
        self.result: JobsSnapshot | JobsFailure | None = None  # the cache of the session
        self.paused = False  # a refused login or a missing command: only a click asks again
        self._clock: Callable[[], float] = time.monotonic
        self._answered_at: float | None = None  # by ``_clock``
        self._index = 0  # which of the user's running jobs the indicator names
        self._stopped = False
        self._pool = QThreadPool()  # no Qt parent (CLAUDE.md, Threading)
        self._pool.setMaxThreadCount(1)
        self._tasks = TaskGroup(self._pool)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.rotation = QTimer(self)
        self.rotation.timeout.connect(self.rotate)
        indicator.clicked.connect(self.on_clicked)
        popup.refresh_requested.connect(self.refresh)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._on_app_state)
        self.start()

    @classmethod
    def for_window(cls, window) -> JobsController:
        """The indicator goes left of the LED; the popup is the window's."""
        indicator = JobsIndicator(window.theme)
        window.top_bar.add_before_led(indicator)
        popup = JobsPopup(window.theme, window)
        return cls(indicator, popup, window.sync, window.config, parent=window)

    @property
    def enabled(self) -> bool:
        """A cluster to sync with and a command to run (spec 64 R4.4)."""
        return self.config.sync_enabled and bool(self.config.cluster.jobs_command)

    @property
    def busy(self) -> bool:
        return self._tasks.active(KEY) is not None

    # -- life ------------------------------------------------------------------------------------
    def start(self) -> None:
        """Show the indicator when enabled, and ask now."""
        self._stopped = False
        cluster = self.config.cluster
        self.poll_timer.setInterval(cluster.jobs_poll_seconds * 1000)
        self.rotation.setInterval(cluster.jobs_rotate_seconds * 1000)
        self.indicator.setVisible(self.enabled)
        if not self.enabled:
            return
        self.poll_timer.start()
        self.query()
        self._show()

    def set_config(self, config: AppConfig) -> None:
        """ "Recarregar config.yaml": the cache, the pause and the timers start over."""
        self.cancel()
        self.config = config
        self.result, self._answered_at, self.paused, self._index = None, None, False, 0
        self.start()

    def cancel(self) -> None:
        """Window close (the "cancelar" step) or a new config: no timer, no query. A running one is
        cancelled and its ssh killed within ``core/sync/command.py:POLL_SECONDS``."""
        self._stopped = True
        self.poll_timer.stop()
        self.rotation.stop()
        self.popup.hide()
        self._tasks.shutdown(0)

    def _on_app_state(self, state: Qt.ApplicationState) -> None:
        if not self.enabled or self._stopped:
            return
        if state == Qt.ApplicationState.ApplicationActive:
            if not self.poll_timer.isActive():
                self.poll_timer.start()
            if self._stale():
                self.poll()
        else:
            self.poll_timer.stop()

    # -- queries ---------------------------------------------------------------------------------
    def poll(self) -> None:
        """The timer: a query, unless paused or one is running."""
        if not self.paused and not self.busy:
            self.query()

    def refresh(self) -> None:
        """ "Atualizar", "Tentar de novo": ask now, paused or not."""
        self.paused = False
        self.query()

    def query(self) -> None:
        if not self.enabled or self._stopped:
            return
        password = self._password()
        if password is None and self._needs_password():
            self._show()  # "Jobs: informe a senha": the click asks
            return
        self._tasks.submit(
            KEY, fetch_jobs, self.config, password, on_done=self._on_result, on_error=self._on_error
        )
        self.popup.set_busy(True)

    def _needs_password(self) -> bool:
        cluster = self.config.cluster
        return cluster.auth == "password" and cluster.resolve_password() is None

    def _password(self) -> str | None:
        """The one typed in this session, when the config has none (``child_env`` reads the
        config's itself)."""
        return self.sync.session_password(ask=False) if self._needs_password() else None

    def _stale(self) -> bool:
        if self._answered_at is None:
            return True
        return self._clock() - self._answered_at > self.config.cluster.jobs_poll_seconds

    def _on_error(self, key: Hashable, error: Exception) -> None:
        log.error("jobs query failed", exc_info=error)
        message = _("Falha ao consultar os jobs: {error}").format(error=error)
        self._on_result(key, JobsFailure(message, local=True))

    def _on_result(self, _key: Hashable, result: JobsSnapshot | JobsFailure) -> None:
        self.result, self._answered_at, self._index = result, self._clock(), 0
        monitor = self.sync.monitor
        if isinstance(result, JobsSnapshot):
            monitor.report(True)
        elif result.connection:
            monitor.report(False)
        elif not (result.auth or result.local):
            monitor.report(True)  # the cluster answered: it is the command that failed
        if isinstance(result, JobsFailure) and (result.auth or result.missing):
            self.paused = True
            if result.auth:
                self.sync.forget_password()
        self._show()
        if self.popup.isVisible():
            self._fill_popup()
        self.fetched.emit(result)

    # -- the indicator and the popup -------------------------------------------------------------
    def rotate(self) -> None:
        """The rotation timer: the next of the user's running jobs."""
        self._index += 1
        self._show()

    def _show(self) -> None:
        cluster = self.config.cluster
        result = self.result
        account = f"{cluster.user}@{cluster.host}"
        mine: tuple[Job, ...] = ()
        if self._needs_password() and self.sync.session_password(ask=False) is None:
            hint = _("Clique para informar a senha de {account} (não é salva).")
            tip = hint.format(account=account)
            if isinstance(result, JobsFailure):
                tip = f"{result.message}\n{tip}"
            text = _("Jobs: informe a senha")
        elif result is None:
            text, tip = _("Consultando jobs…"), _("Consultando a fila do cluster ({account})…")
            tip = tip.format(account=account)
        elif isinstance(result, JobsFailure):
            text, tip = _("Jobs indisponíveis"), result.message
        else:
            mine = result.mine(cluster.user)
            if mine:
                name = mine[self._index % len(mine)].name
                text = _("Executando: {name}").format(name=name)
            else:
                text = _("Nenhum job em execução")
            tip = _(
                "Seus jobs: {running} em execução, {waiting} na fila · atualizado às {time}. "
                "Clique para ver a fila do cluster."
            ).format(
                running=len(mine),
                waiting=len(result.queued(cluster.user)),
                time=clock(result.fetched_at),
            )
        if len(mine) > 1:
            if not self.rotation.isActive():
                self.rotation.start()
        else:
            self.rotation.stop()
        self.indicator.set_text(text, tip)

    def on_clicked(self) -> None:
        """The queue, from the cache; asked again in the background when it is old. Without a
        password, the sync's dialog asks for it first."""
        if self._needs_password() and self.sync.session_password(ask=False) is None:
            if self.sync.session_password(ask=True) is None:
                return
            self.refresh()
        elif not self.paused and not self.busy and self._stale():
            self.query()
        self._fill_popup()
        self.popup.popup_below(self.indicator)

    def _fill_popup(self) -> None:
        result = self.result
        if isinstance(result, JobsSnapshot):
            self.popup.show_snapshot(result, self.config.cluster.user)
        elif isinstance(result, JobsFailure):
            self.popup.show_failure(result.message)
        else:
            self.popup.show_loading()
        self.popup.set_busy(self.busy)
