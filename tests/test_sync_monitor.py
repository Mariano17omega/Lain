import socket
import threading
import time

from PyQt6 import sip

from qe_studio.core.config import parse_config
from qe_studio.core.sync import monitor as monitor_module
from qe_studio.core.sync.monitor import ConnectionMonitor, ConnectionState, probe


def listening_socket():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    return server


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_probe():
    with listening_socket() as server:
        assert probe("127.0.0.1", server.getsockname()[1], timeout=1)
    assert not probe("127.0.0.1", free_port(), timeout=1)


def test_probe_ssh_server(ssh_server):
    server, _remote = ssh_server
    assert probe(server.host, server.port, timeout=2)
    assert not probe("127.0.0.1", free_port(), timeout=1)


def test_monitor_online_for_the_ssh_server(qtbot, ssh_server):
    server, _remote = ssh_server
    # The probe goes to cluster.host:port, so the monitor is given the address, not the alias.
    cluster = parse_config(server.config_data(host=server.host)).cluster
    monitor = ConnectionMonitor(cluster, enabled=True)
    with qtbot.waitSignal(monitor.state_changed, timeout=5000) as blocker:
        monitor.start()
    assert blocker.args == [ConnectionState.ONLINE.value]
    monitor.stop()
    server.close()
    monitor.report(probe(server.host, server.port, timeout=1))
    assert monitor.state is ConnectionState.OFFLINE


def test_monitor_states(qtbot):
    with listening_socket() as server:
        cluster = parse_config(
            {"cluster": {"host": "127.0.0.1", "user": "me", "port": server.getsockname()[1]}}
        ).cluster
        monitor = ConnectionMonitor(cluster, enabled=True)
        with qtbot.waitSignal(monitor.state_changed, timeout=5000) as blocker:
            monitor.start()
        assert blocker.args == [ConnectionState.ONLINE.value]
        monitor.set_syncing(True)
        assert monitor.state is ConnectionState.SYNCING
        monitor.check()  # ignored while syncing
        monitor.set_syncing(False)
        monitor.report(False)
        assert monitor.state is ConnectionState.OFFLINE
        monitor.stop()


def test_monitor_disabled_without_cluster():
    monitor = ConnectionMonitor(parse_config({}).cluster, enabled=True)
    assert monitor.state is ConnectionState.DISABLED
    monitor.start()
    monitor.check()
    assert monitor.state is ConnectionState.DISABLED


def test_stuck_probe_blocks_neither_stop_nor_delete(qtbot, monkeypatch):
    """The connect timeout does not cover DNS: reload and exit must not wait for a lookup."""
    release = threading.Event()
    started = threading.Event()

    def stuck(host, port):
        started.set()
        return release.wait(10)

    monkeypatch.setattr(monitor_module, "probe", stuck)
    cluster = parse_config({"cluster": {"host": "cluster.test", "user": "me"}}).cluster
    monitor = ConnectionMonitor(cluster, enabled=True)
    monitor.start()
    assert started.wait(5)
    begin = time.monotonic()
    monitor.stop()
    sip.delete(monitor)  # what reload_config's deleteLater does
    assert time.monotonic() - begin < 0.5
    release.set()
    qtbot.wait(50)  # the late result must not reach the deleted monitor
