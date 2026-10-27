"""One ssh connection for many commands (spec 72): ``core/sync/mux.py`` on its own, then the real
``ssh`` with ``ControlMaster`` against the local paramiko server (``tests/ssh_server.py``).

Nothing reaches the cluster: every ssh goes to ``127.0.0.1`` (the guard of ``tests/cluster_guard.py``
still watches), the sockets live in the test's short ``XDG_RUNTIME_DIR`` (``tests/conftest.py``) and
the server stops the masters before it closes (``LocalSSHServer.close``).
"""

import logging
import os
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from qe_studio.core.cluster_jobs import JobsSnapshot, fetch_jobs
from qe_studio.core.config import parse_config
from qe_studio.core.remote.listing import list_remote
from qe_studio.core.sync import mux
from qe_studio.core.sync.command import remote_command, run_command
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.push import PushController
from qe_studio.core.sync.rsync import Endpoint, child_env

from jobs_helpers import QSTATUS_ALL
from ssh_server import HOST_ALIAS, PASSWORD, USER, AuthAttempt, LocalSSHServer
from sync_helpers import T0, run_push, run_sync, write

NO_CONFIG_SSH = f"ssh -F {os.devnull}"  # never the user's ~/.ssh

needs_ssh = pytest.mark.skipif(shutil.which("ssh") is None, reason="ssh is required")


def cluster(multiplex: bool = True):
    return parse_config({"cluster": {"host": "hpc.example", "user": "me", "multiplex": multiplex}})


def runtime_dir() -> Path:
    return Path(os.environ["XDG_RUNTIME_DIR"])  # the test's own (conftest)


def runtime_for(monkeypatch, length: int) -> Path:
    """Point ``XDG_RUNTIME_DIR`` at a folder that makes ``control_dir()`` ``length`` characters."""
    pad = length - len(str(runtime_dir())) - len(mux.FOLDER) - 2
    folder = runtime_dir() / ("a" * pad)
    folder.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(folder))
    expected = folder / mux.FOLDER
    assert len(str(expected)) == length
    return expected


def wait_for(condition, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


# -- the module (no network) -----------------------------------------------------------------------


def test_the_options_of_the_shared_connection():
    folder = mux.control_dir()
    assert folder == runtime_dir() / "qe-studio-mux"
    assert mux.options(cluster().cluster) == [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={folder}/%C",
        "-o",
        "ControlPersist=120",
    ]


def test_no_options_when_it_is_turned_off():
    assert mux.options(cluster(multiplex=False).cluster) == []


def test_no_options_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert mux.control_dir() is None
    assert mux.options(cluster().cluster) == []


def test_no_options_when_the_folder_path_is_too_long(monkeypatch):
    folder = runtime_for(monkeypatch, mux.MAX_DIR_CHARS + 1)
    assert mux.control_dir() is None
    assert mux.options(cluster().cluster) == []
    assert not folder.exists()  # nothing is made where a socket would not fit


def test_no_options_when_the_folder_is_a_link(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    (runtime_dir() / mux.FOLDER).symlink_to(target)
    assert mux.control_dir() is None
    assert mux.options(cluster().cluster) == []


def test_no_options_when_the_folder_belongs_to_someone_else(monkeypatch):
    (runtime_dir() / mux.FOLDER).mkdir(mode=0o700)
    uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    assert mux.control_dir() is None
    assert mux.options(cluster().cluster) == []


def test_the_folder_is_made_private():
    folder = mux.control_dir()
    assert folder is not None
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_an_open_folder_of_the_user_is_made_private():
    folder = runtime_dir() / mux.FOLDER
    folder.mkdir()
    folder.chmod(0o755)
    assert mux.control_dir() == folder
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


@pytest.mark.parametrize("runtime", [None, "relative/run"])
def test_without_a_runtime_folder_the_temp_folder_holds_one_per_user(monkeypatch, runtime):
    temp = runtime_dir()  # short and the test's own: stands for /tmp
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp))
    if runtime is None:
        monkeypatch.delenv("XDG_RUNTIME_DIR")
    else:
        monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)  # not absolute: ignored
    assert mux.control_dir() == temp / f"qe-studio-mux-{os.getuid()}"


def test_a_folder_removed_while_lain_runs_is_made_again():
    folder = mux.control_dir()
    assert folder is not None
    folder.rmdir()  # a tmp cleaner: ssh could not bind its socket there
    assert mux.control_dir() == folder
    assert folder.is_dir()


def test_close_all_without_sockets_runs_nothing(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("no master to stop")

    monkeypatch.setattr(subprocess, "run", never)
    folder = mux.control_dir()
    assert folder is not None
    (folder / "not-a-socket").write_text("")
    assert mux.close_all("ssh", 1.0) is True
    monkeypatch.setattr(sys, "platform", "win32")  # no folder at all
    assert mux.close_all("ssh", 1.0) is True


def test_close_all_without_an_ssh_to_run_does_not_raise(caplog):
    folder = mux.control_dir()
    assert folder is not None
    dead = socket.socket(socket.AF_UNIX)
    dead.bind(str(folder / "dead"))
    dead.close()
    assert mux.close_all("/no/such/ssh", 1.0) is True
    assert "cannot stop" in caplog.text


@needs_ssh
def test_close_all_skips_a_dead_socket():
    folder = mux.control_dir()
    assert folder is not None
    dead = socket.socket(socket.AF_UNIX)
    dead.bind(str(folder / "dead"))
    dead.close()  # the socket file stays, nobody listens: a master killed with SIGKILL
    assert mux.sockets(folder) == [folder / "dead"]
    assert mux.close_all(NO_CONFIG_SSH, 5.0) is True


# -- the real ssh against the test server ----------------------------------------------------------


@pytest.fixture
def server(ssh_keys, tmp_path):
    """A server with a ``qstatus`` (prints ``QSTATUS_ALL``) and ``sleep``; its masters are stopped
    by ``server.close()``."""
    if shutil.which("rsync") is None or shutil.which("ssh") is None:
        pytest.skip("rsync and ssh are required")
    remote, workdir = tmp_path / "cluster", tmp_path / "ssh"
    remote.mkdir()
    workdir.mkdir()
    script = tmp_path / "qstatus.py"
    script.write_text(f"import sys\nsys.stdout.write({QSTATUS_ALL!r})\n")
    commands = {"qstatus": [sys.executable, str(script)], "sleep": ["sleep"]}
    server = LocalSSHServer(remote, ssh_keys, workdir, commands=commands)
    yield server
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"
    folder = mux.control_dir()
    assert folder is None or mux.sockets(folder) == [], "an ssh master outlived the test"


def shared(server: LocalSSHServer, **options):
    return parse_config(server.config_data(multiplex=True, **options))


def run(config, command: str, password: str | None = None):
    env = child_env(config.cluster, password=password)
    return run_command(remote_command(config, command), env, 30)


def master_socket() -> Path:
    folder = mux.control_dir()
    assert folder is not None
    (path,) = mux.sockets(folder)
    return path


def check(path: Path) -> subprocess.CompletedProcess:
    """``ssh -O check`` on the socket: 0 and "Master running (pid=N)" while the master lives."""
    argv = [*shlex.split(NO_CONFIG_SSH), "-O", "check", "-S", str(path), "localhost"]
    return subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)


def test_one_login_for_many_commands(server):
    """R4.1: three commands, a listing and the queue go through one login."""
    write(server.root, "scf.in", "scf")
    config = shared(server)
    for n in range(3):
        result = run(config, f"echo {n}")
        assert (result.code, result.stdout) == (0, f"{n}\n"), result.stderr
    listing = list_remote(config, str(server.root))
    assert isinstance(listing, list) and [e.name for e in listing] == ["scf.in"]
    assert isinstance(fetch_jobs(config), JobsSnapshot)
    assert len(server.attempts) == 1
    commands = server.commands()
    assert commands[:3] == ["echo 0", "echo 1", "echo 2"] and len(commands) == 5
    assert commands[3].startswith("rsync --server") and commands[4] == "qstatus -a"


def test_a_command_does_not_wait_for_the_master(server):
    """R4.2: the master keeps the connection 120 s, never the pipes of the command."""
    config = shared(server)
    start = time.monotonic()
    for _ in range(3):
        assert run(config, "true").code == 0
    assert time.monotonic() - start < 5
    assert len(server.attempts) == 1 and check(master_socket()).returncode == 0


def test_pull_and_push_share_the_master(qtbot, tmp_path, server):
    """R4.2: rsync through ``QProcess`` ends without waiting for the master, with one login."""
    config = shared(server)
    endpoint = Endpoint(str(server.root), HOST_ALIAS, USER)
    write(server.root, "scf.out", "scf", T0)
    local = tmp_path / "local"
    report, _ = run_sync(qtbot, SyncController(config), local, endpoint)
    assert report.status is SyncStatus.DONE, report.error
    assert (local / "scf.out").read_text() == "scf"
    write(local, "bands.in", "bands")
    report = run_push(qtbot, PushController(config), local, endpoint)
    assert report.status is SyncStatus.DONE, report.error
    assert (server.root / "bands.in").read_text() == "bands"
    assert len(server.attempts) == 1
    assert len(server.commands()) == 4  # dry run and transfer, twice


def test_the_password_is_asked_once(server, caplog, monkeypatch):
    """R4.3: only the ssh that opens the master runs the askpass; the password stays off argv and
    the log."""
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    caplog.set_level(logging.DEBUG)
    config = shared(server, auth="password", password_env="LAIN_NO_PW")
    for _ in range(3):
        assert isinstance(fetch_jobs(config, password=PASSWORD), JobsSnapshot)
    assert server.attempts == [AuthAttempt(USER, "password", True)]
    assert {r.method for r in server.log} == {"password"} and len(server.log) == 3
    assert PASSWORD not in shlex.join(remote_command(config, "qstatus -a"))
    assert "qstatus -a" in caplog.text and PASSWORD not in caplog.text


def test_a_dead_socket_is_replaced_by_the_next_command(server):
    """R4.4: a master killed with SIGKILL leaves its socket; the next ssh logs in again."""
    config = shared(server)
    assert run(config, "true").code == 0
    path = master_socket()
    match = re.search(r"pid=(\d+)", check(path).stderr)
    assert match is not None
    os.kill(int(match.group(1)), signal.SIGKILL)
    wait_for(lambda: server.open_connections() == 0)  # dead: its connection is gone
    assert path.exists()  # SIGKILL: no clean-up
    result = run(config, "echo again")
    assert (result.code, result.stdout) == (0, "again\n"), result.stderr
    assert len(server.attempts) == 2
    assert check(master_socket()).returncode == 0  # a new master in its place


def test_a_refused_session_logs_in_by_itself_and_runs_once(server):
    """R4.5: the cluster's MaxSessions refuses a session of the master: ssh logs in by itself and
    the command runs once."""
    config = shared(server)
    server.max_sessions = 1
    held = []
    holder = threading.Thread(target=lambda: held.append(run(config, "sleep 3")))
    holder.start()
    wait_for(lambda: "sleep 3" in server.commands())  # the master's one session is taken
    result = run(config, "echo once")
    holder.join(15)
    assert (result.code, result.stdout) == (0, "once\n"), result.stderr
    assert "Session open refused by peer" in result.stderr  # refused by the master's connection
    assert server.commands().count("echo once") == 1
    assert len(server.attempts) == 2
    assert [r.code for r in held] == [0]


@pytest.mark.parametrize("known_hosts", ["other", "empty"])
def test_the_host_key_is_still_required(server, known_hosts):
    """R4.6: a changed or unknown host key refuses the command as before, and no master is born."""
    config = shared(server, known_hosts=known_hosts)
    result = run(config, "true")
    assert result.code == 255 and "Host key verification failed" in result.stderr
    if known_hosts == "other":
        assert "REMOTE HOST IDENTIFICATION HAS CHANGED" in result.stderr
    folder = mux.control_dir()
    assert folder is not None and mux.sockets(folder) == []
    assert server.attempts == [] and server.log == []


def test_close_all_stops_the_master(server):
    """R4.7: after ``close_all`` the socket is gone, the master leaves and a new command logs in."""
    config = shared(server)
    assert run(config, "true").code == 0
    path = master_socket()
    assert mux.close_all(NO_CONFIG_SSH, 5.0) is True
    folder = mux.control_dir()
    assert folder is not None and mux.sockets(folder) == []  # removed before it answered
    assert check(path).returncode != 0
    wait_for(lambda: server.open_connections() == 0)  # no session left: the master exited
    assert run(config, "true").code == 0
    assert len(server.attempts) == 2


def test_the_longest_folder_still_holds_a_master(server, monkeypatch):
    """R4.8: a folder of ``MAX_DIR_CHARS`` characters fits the socket path."""
    folder = runtime_for(monkeypatch, mux.MAX_DIR_CHARS)
    config = shared(server)
    assert mux.control_dir() == folder
    for _ in range(2):
        result = run(config, "true")
        assert result.code == 0, result.stderr
    assert len(mux.sockets(folder)) == 1 and len(server.attempts) == 1


def test_one_character_more_and_every_ssh_logs_in(server, monkeypatch):
    """R4.8: one character over and there is no master; the commands still work."""
    runtime_for(monkeypatch, mux.MAX_DIR_CHARS + 1)
    config = shared(server)
    assert mux.options(config.cluster) == []
    for _ in range(2):
        assert run(config, "true").code == 0
    assert len(server.attempts) == 2
