"""Pulls over a real ssh connection to the local paramiko server (spec 7, R7).

The real ``ssh`` and ``rsync`` run, so the options ``core/sync/rsync.py`` builds (``-p``,
``ConnectTimeout``, ``BatchMode``, ``-i``/``IdentitiesOnly``, ``NumberOfPasswordPrompts``), the
``SSH_ASKPASS`` helper and the refusal of unknown host keys are all exercised. The client never
reads ``~/.ssh``: ``ssh`` is pinned to a temp ``ssh_config`` (see ``ssh_server.py``).
"""

import logging
import os
import socket
import time

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.rsync import Endpoint

from ssh_server import HOST_ALIAS, PASSWORD, USER
from sync_helpers import T0, run_sync, write


def pull(qtbot, tmp_path, ssh_server, password=None, timeout=30_000, **options):
    """Pull the served folder into ``tmp_path/local``. ``options`` go to ``config_data``."""
    server, remote = ssh_server
    local = tmp_path / "local"
    config = parse_config(server.config_data(**options))
    controller = SyncController(config, password=password)
    report, _ = run_sync(
        qtbot, controller, local, Endpoint(str(remote), HOST_ALIAS, USER), timeout=timeout
    )
    return report, local


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_key_auth_pull(qtbot, tmp_path, ssh_server):
    server, remote = ssh_server
    write(remote, "scf.out", "scf", T0)
    write(remote, "sub/bands.dat.gnu", "gnu", T0 + 60)
    report, local = pull(qtbot, tmp_path, ssh_server)

    assert report.status is SyncStatus.DONE, report.error
    assert sorted(report.transferred) == ["scf.out", "sub/bands.dat.gnu"]
    assert (local / "sub/bands.dat.gnu").read_text() == "gnu"
    assert abs((local / "scf.out").stat().st_mtime - T0) < 1
    assert abs((local / "sub/bands.dat.gnu").stat().st_mtime - (T0 + 60)) < 1
    # Only -i <key> (+ IdentitiesOnly) offers the key: the ssh_config has none and no agent.
    assert {(r.user, r.method) for r in server.log} == {(USER, "publickey")}
    assert all(c.startswith("rsync --server") for c in server.commands())


def test_key_rejected_fails_without_a_password_prompt(qtbot, tmp_path, ssh_server):
    """BatchMode=yes: ssh never falls back to asking for a password (it would hang the sync)."""
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    server.reject_auth = True
    report, local = pull(qtbot, tmp_path, ssh_server, timeout=15_000)
    assert report.status is SyncStatus.FAILED
    assert "Autenticação" in report.error
    assert not report.connection_failed
    assert not local.exists()
    assert server.log == []


def test_password_pull_through_askpass(qtbot, tmp_path, ssh_server, caplog):
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    caplog.set_level(logging.DEBUG)
    report, local = pull(qtbot, tmp_path, ssh_server, password=PASSWORD, auth="password")

    assert report.status is SyncStatus.DONE, report.error
    assert (local / "scf.out").read_text() == "scf"
    assert {r.method for r in server.log} == {"password"}
    assert [a.method for a in server.attempts if a.accepted] == ["password"] * 2
    # The secret travels in the child environment only: never in a logged command line.
    assert "rsync" in caplog.text and PASSWORD not in caplog.text


def test_wrong_password_fails_and_creates_nothing(qtbot, tmp_path, ssh_server):
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    report, local = pull(qtbot, tmp_path, ssh_server, password="wrong", auth="password")

    assert report.status is SyncStatus.FAILED
    assert "Autenticação" in report.error
    assert not report.connection_failed
    assert not local.exists()
    assert server.log == []
    assert [a.accepted for a in server.attempts] == [False]  # NumberOfPasswordPrompts=1


@pytest.mark.parametrize(
    ("auth", "strict"),
    [
        ("key", "yes"),
        ("key", "ask"),  # BatchMode=yes: ssh cannot ask, so it refuses
        ("password", "ask"),  # ssh never asks: StrictHostKeyChecking=yes (askpass would say "no")
    ],
)
def test_unknown_host_key_is_refused(qtbot, tmp_path, ssh_server, auth, strict):
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    report, local = pull(
        qtbot,
        tmp_path,
        ssh_server,
        password=PASSWORD,
        auth=auth,
        strict=strict,
        known_hosts="empty",
    )
    assert report.status is SyncStatus.FAILED
    assert "Chave do host" in report.error
    assert not local.exists()
    assert server.attempts == [] and server.log == []  # refused before authenticating


@pytest.mark.parametrize("auth", ["key", "password"])
@pytest.mark.parametrize("strict", ["no", "accept-new"])
def test_a_permissive_ssh_config_cannot_accept_an_unknown_host(
    qtbot, tmp_path, ssh_server, auth, strict
):
    """ssh_config says ``StrictHostKeyChecking no`` / ``accept-new`` for the host: Lain's ``-o``
    still wins (spec 27-3 R1), nothing is learned and nobody authenticates."""
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    report, local = pull(
        qtbot,
        tmp_path,
        ssh_server,
        password=PASSWORD,
        auth=auth,
        strict=strict,
        known_hosts="empty",
    )
    assert report.status is SyncStatus.FAILED
    assert "Chave do host" in report.error
    assert not local.exists()
    assert server.attempts == [] and server.log == []
    assert (server.workdir / "known_hosts").read_text() == ""


@pytest.mark.parametrize("strict", ["yes", "ask"])
def test_changed_host_key_is_refused(qtbot, tmp_path, ssh_server, strict):
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    report, local = pull(qtbot, tmp_path, ssh_server, strict=strict, known_hosts="other")
    assert report.status is SyncStatus.FAILED
    assert "Chave do host" in report.error
    assert not local.exists()
    assert server.attempts == [] and server.log == []


def test_closed_port_is_reported_as_refused(qtbot, tmp_path, ssh_server):
    """``-p`` from the Lain config wins over the ssh_config Port, which points at the server."""
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    report, _local = pull(qtbot, tmp_path, ssh_server, port=free_port())
    assert report.status is SyncStatus.FAILED
    assert report.error == "Conexão recusada pelo cluster (verifique a porta SSH)."
    assert report.connection_failed
    assert server.log == []


def test_stalled_banner_times_out_within_connect_timeout(qtbot, tmp_path, ssh_server):
    server, remote = ssh_server
    write(remote, "scf.out", "scf")
    server.stall_banner = True
    start = time.monotonic()
    report, local = pull(qtbot, tmp_path, ssh_server, timeout=20_000, connect_timeout=2)

    assert report.status is SyncStatus.FAILED
    assert report.connection_failed
    assert "tempo de conexão esgotado" in report.error
    assert 1.5 < time.monotonic() - start < 12  # ConnectTimeout=2 reached ssh, not rsync's 60 s
    assert not local.exists()


def test_connection_dropped_mid_transfer_leaves_no_partial_file(qtbot, tmp_path, ssh_server):
    server, remote = ssh_server
    (remote / "big.out").write_bytes(os.urandom(4 * 1024 * 1024))
    # The dry run (a file listing) fits well below the limit, so only the transfer is cut.
    server.drop_after_bytes = 1024 * 1024
    report, local = pull(qtbot, tmp_path, ssh_server)

    assert report.status is SyncStatus.FAILED
    assert report.connection_failed
    assert "Conexão interrompida" in report.error
    assert not (local / "big.out").exists()
    assert [p.name for p in local.iterdir()] == []  # no temp file either
    assert [r.status for r in server.log] == [0, None]  # dry run done, transfer dropped
