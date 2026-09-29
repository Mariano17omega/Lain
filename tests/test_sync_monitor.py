import socket

from qe_studio.config import parse_config
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
