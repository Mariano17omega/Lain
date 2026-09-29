"""Cluster reachability indicator (PRD §2.1 activity bar LED).

Probes are plain TCP connects to the SSH port (no login), at most every
``cluster.status_poll_seconds`` and only while the app window is active: frequent
pre-authentication disconnects can trip fail2ban on the cluster.
"""

from __future__ import annotations

import socket
import time
from enum import StrEnum

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication

from ...config import ClusterConfig

PROBE_TIMEOUT = 3.0


class ConnectionState(StrEnum):
    DISABLED = "disabled"  # cluster not configured
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    SYNCING = "syncing"


def probe(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class _ProbeSignals(QObject):
    done = pyqtSignal(bool)


class _Probe(QRunnable):
    def __init__(self, host: str, port: int):
        super().__init__()
        self.host, self.port = host, port
        self.signals = _ProbeSignals()

    def run(self) -> None:
        self.signals.done.emit(probe(self.host, self.port))


class ConnectionMonitor(QObject):
    state_changed = pyqtSignal(str)

    def __init__(self, cluster: ClusterConfig, enabled: bool, parent: QObject | None = None):
        super().__init__(parent)
        self.cluster = cluster
        self.enabled = enabled and cluster.configured
        self._state = ConnectionState.UNKNOWN if self.enabled else ConnectionState.DISABLED
        self._syncing = False
        self._probing = False
        self._last_probe = 0.0
        self._probes: list[_Probe] = []
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._timer = QTimer(self)
        self._timer.setInterval(max(cluster.status_poll_seconds, 30) * 1000)
        self._timer.timeout.connect(self.check)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._on_app_state)

    @property
    def state(self) -> ConnectionState:
        return ConnectionState.SYNCING if self._syncing else self._state

    def start(self) -> None:
        if self.enabled:
            self._timer.start()
            self.check()

    def stop(self) -> None:
        """Stop polling and wait for an in-flight probe (must not outlive the app)."""
        self._timer.stop()
        self._pool.waitForDone(int(PROBE_TIMEOUT * 1000) + 500)

    @pyqtSlot()
    def check(self) -> None:
        if not self.enabled or self._probing or self._syncing:
            return
        self._probing = True
        self._last_probe = time.monotonic()
        runnable = _Probe(self.cluster.host, self.cluster.port)
        runnable.signals.done.connect(self._on_probe)
        self._probes.append(runnable)  # keep the signal object alive until it fires
        self._pool.start(runnable)

    def set_syncing(self, syncing: bool) -> None:
        self._syncing = syncing
        self.state_changed.emit(self.state.value)

    def report(self, reachable: bool) -> None:
        """Feed the outcome of a real sync (cheaper and more accurate than a probe)."""
        self._set(ConnectionState.ONLINE if reachable else ConnectionState.OFFLINE)

    def _on_probe(self, reachable: bool) -> None:
        self._probing = False
        # Release finished probes later: this slot runs on the probe's own signal object.
        QTimer.singleShot(0, self._release_probes)
        self.report(reachable)

    def _release_probes(self) -> None:
        if not self._probing:
            self._probes.clear()

    def _set(self, state: ConnectionState) -> None:
        changed = state != self._state
        self._state = state
        if changed or not self._syncing:
            self.state_changed.emit(self.state.value)

    def _on_app_state(self, state) -> None:
        from PyQt6.QtCore import Qt

        if not self.enabled:
            return
        if state == Qt.ApplicationState.ApplicationActive:
            if not self._timer.isActive():
                self._timer.start()
            if time.monotonic() - self._last_probe > self._timer.interval() / 1000:
                self.check()
        else:
            self._timer.stop()
