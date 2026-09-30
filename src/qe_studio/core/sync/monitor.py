"""Cluster reachability indicator (PRD §2.1 activity bar LED).

Probes are plain TCP connects to the SSH port (no login), at most every
``cluster.status_poll_seconds`` and only while the app window is active: frequent
pre-authentication disconnects can trip fail2ban on the cluster.

Each probe runs in a daemon thread, not a ``QThreadPool``: the connect timeout does not cover
the DNS lookup, which can block much longer (VPN or resolver down), and a pool waits for its
running task, without a time limit, when it is destroyed (config reload, exit).
"""

from __future__ import annotations

import socket
import threading
import time
from enum import StrEnum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication

from ..config import ClusterConfig

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


def _run_probe(signals: _ProbeSignals, host: str, port: int) -> None:
    signals.done.emit(probe(host, port))


class ConnectionMonitor(QObject):
    state_changed = pyqtSignal(str)

    def __init__(self, cluster: ClusterConfig, enabled: bool, parent: QObject | None = None):
        super().__init__(parent)
        self.cluster = cluster
        self.enabled = enabled and cluster.configured
        self._state = ConnectionState.UNKNOWN if self.enabled else ConnectionState.DISABLED
        self._syncing = False
        self._stopped = False
        self._probing = False
        self._last_probe = 0.0
        # Signal objects of the probe threads, released on the GUI thread once each has ended.
        self._probes: list[tuple[threading.Thread, _ProbeSignals]] = []
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
        self._stopped = False
        if self.enabled:
            self._timer.start()
            self.check()

    def stop(self) -> None:
        """Stop polling. An in-flight probe is not waited for: its daemon thread cannot keep
        the app from exiting, and its result no longer reaches a deleted monitor."""
        self._stopped = True
        self._timer.stop()

    @pyqtSlot()
    def check(self) -> None:
        if not self.enabled or self._probing or self._syncing:
            return
        self._probing = True
        self._last_probe = time.monotonic()
        self._release_probes()
        signals = _ProbeSignals()
        signals.done.connect(self._on_probe)
        thread = threading.Thread(
            target=_run_probe,
            args=(signals, self.cluster.host, self.cluster.port),
            name="lain-probe",
            daemon=True,
        )
        self._probes.append((thread, signals))
        thread.start()

    def set_syncing(self, syncing: bool) -> None:
        self._syncing = syncing
        self.state_changed.emit(self.state.value)

    def report(self, reachable: bool) -> None:
        """Feed the outcome of a real sync (cheaper and more accurate than a probe)."""
        self._set(ConnectionState.ONLINE if reachable else ConnectionState.OFFLINE)

    def _on_probe(self, reachable: bool) -> None:
        self._probing = False
        self.report(reachable)

    def _release_probes(self) -> None:
        # Only ended threads: the last reference to a signal object must go on this thread,
        # and not while its slot runs, so this is called from check(), never from _on_probe.
        self._probes = [(t, s) for t, s in self._probes if t.is_alive()]

    def _set(self, state: ConnectionState) -> None:
        changed = state != self._state
        self._state = state
        if changed or not self._syncing:
            self.state_changed.emit(self.state.value)

    def _on_app_state(self, state) -> None:
        from PyQt6.QtCore import Qt

        if not self.enabled or self._stopped:  # regaining focus must not restart a stopped monitor
            return
        if state == Qt.ApplicationState.ApplicationActive:
            if not self._timer.isActive():
                self._timer.start()
            if time.monotonic() - self._last_probe > self._timer.interval() / 1000:
                self.check()
        else:
            self._timer.stop()
