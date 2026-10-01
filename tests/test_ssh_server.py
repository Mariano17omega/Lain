"""The test SSH server itself: authentication, command allowlist, failure modes, shutdown.

Driven with a paramiko client, so these run without the ``ssh`` and ``rsync`` binaries.
"""

import socket
from contextlib import closing

import paramiko
import pytest

from ssh_server import PASSWORD, USER, LocalSSHServer


@pytest.fixture
def server(ssh_keys, tmp_path):
    root = tmp_path / "cluster"
    root.mkdir()
    workdir = tmp_path / "ssh"
    workdir.mkdir()
    server = LocalSSHServer(root, ssh_keys, workdir)
    yield server
    server.close()
    assert not server.alive_threads()


def connect(server, **auth) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        server.host,
        server.port,
        username=auth.pop("username", USER),
        allow_agent=False,
        look_for_keys=False,
        timeout=5,
        **auth,
    )
    return client


def run(client: paramiko.SSHClient, command: str) -> tuple[int, bytes, bytes]:
    _stdin, stdout, stderr = client.exec_command(command)
    out, err = stdout.read(), stderr.read()
    return stdout.channel.recv_exit_status(), out, err


def test_public_key_auth_and_probe_command(server, ssh_keys):
    with closing(connect(server, pkey=ssh_keys.client_key)) as client:
        assert client.get_transport().get_remote_server_key() == ssh_keys.host_key
        assert run(client, "echo hello 'two words'") == (0, b"hello two words\n", b"")
        assert run(client, "true")[0] == 0
    assert [(r.user, r.method, r.command, r.status) for r in server.log] == [
        (USER, "publickey", "echo hello 'two words'", 0),
        (USER, "publickey", "true", 0),
    ]


def test_password_auth(server):
    with closing(connect(server, password=PASSWORD)) as client:
        assert run(client, "echo ok")[0] == 0
    assert server.log[0].method == "password"
    assert server.attempts[-1].accepted


def test_wrong_password_and_wrong_user_are_rejected(server):
    with pytest.raises(paramiko.AuthenticationException):
        connect(server, password="nope")
    with pytest.raises(paramiko.AuthenticationException):
        connect(server, username="someone-else", password=PASSWORD)
    assert [a.accepted for a in server.attempts] == [False, False]
    assert server.log == []


def test_unknown_client_key_is_rejected(server, ssh_keys):
    with pytest.raises(paramiko.AuthenticationException):
        connect(server, pkey=ssh_keys.other_host_key)


def test_reject_auth_fails_every_method(server, ssh_keys):
    server.reject_auth = True
    with pytest.raises(paramiko.AuthenticationException):
        connect(server, password=PASSWORD)
    with pytest.raises(paramiko.AuthenticationException):
        connect(server, pkey=ssh_keys.client_key)


def test_command_outside_the_allowlist_is_refused_not_run(server, ssh_keys):
    with closing(connect(server, pkey=ssh_keys.client_key)) as client:
        status, out, err = run(client, "touch should-not-exist")
        assert (status, out) == (127, b"")
        assert b"not allowed" in err
        assert run(client, "sh -c 'touch should-not-exist'")[0] == 127
        assert run(client, "echo fine; touch should-not-exist")[1:] == (
            b"fine; touch should-not-exist\n",
            b"",
        )  # no shell: the ';' is just an argument of echo
    assert not (server.root / "should-not-exist").exists()
    assert server.commands() == ["echo fine; touch should-not-exist"]
    assert len(server.commands(allowed_only=False)) == 3
    assert [r.allowed for r in server.log] == [False, False, True]


def test_rsync_server_commands_run_in_the_served_folder(server, ssh_keys, monkeypatch):
    # Not a real transfer: ``rsync --server`` with no valid options exits with an error,
    # which proves it was started (and not refused with 127).
    with closing(connect(server, pkey=ssh_keys.client_key)) as client:
        status, _out, _err = run(client, "rsync --server --no-such-option .")
    assert status not in (0, 127)
    assert server.log[0].allowed


def test_drop_after_bytes_cuts_the_channel_without_exit_status(server, ssh_keys):
    server.drop_after_bytes = 100
    with closing(connect(server, pkey=ssh_keys.client_key)) as client:
        _stdin, stdout, _stderr = client.exec_command("echo " + "x" * 5000)
        assert len(stdout.read()) == 100
        assert stdout.channel.recv_exit_status() == -1  # connection ended with no status
    assert server.log[0].status is None


def test_stall_banner_accepts_tcp_and_stays_silent(server):
    server.stall_banner = True
    with socket.create_connection((server.host, server.port), timeout=2) as sock:
        sock.settimeout(0.5)
        with pytest.raises(TimeoutError):
            sock.recv(1)


def test_close_stops_everything(ssh_keys, tmp_path):
    (tmp_path / "root").mkdir()
    (tmp_path / "work").mkdir()
    server = LocalSSHServer(tmp_path / "root", ssh_keys, tmp_path / "work")
    server.stall_banner = True
    stalled = socket.create_connection((server.host, server.port), timeout=2)
    server.stall_banner = False
    client = connect(server, pkey=ssh_keys.client_key)
    assert run(client, "true")[0] == 0
    server.close()
    stalled.close()
    client.close()
    assert server.alive_threads() == []
    with pytest.raises(OSError):
        socket.create_connection((server.host, server.port), timeout=1)
