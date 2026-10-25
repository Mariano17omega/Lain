"""The job list over a real ssh connection to the local paramiko server (spec 64 R7).

A fake ``qstatus`` (a Python script that prints the listing of the spec) is the server's own
command; the real ``ssh`` runs with the options of ``core/sync/rsync.py:ssh_command``, by key and
by password (``SSH_ASKPASS``). The password never reaches an argv or the log.
"""

import logging
import shutil
import sys

import pytest

from qe_studio.core import cluster_jobs
from qe_studio.core.cluster_jobs import JobsFailure, JobsSnapshot, fetch_jobs
from qe_studio.core.config import parse_config
from qe_studio.core.sync.askpass import SECRET_ENV

from jobs_helpers import QSTATUS_ALL
from ssh_server import PASSWORD, USER, LocalSSHServer


@pytest.fixture
def server(ssh_keys, tmp_path):
    """A server whose ``qstatus`` prints ``QSTATUS_ALL`` and its own arguments on stderr."""
    if shutil.which("ssh") is None:
        pytest.skip("ssh is required")
    remote, workdir = tmp_path / "cluster", tmp_path / "ssh"
    remote.mkdir()
    workdir.mkdir()
    script = tmp_path / "qstatus.py"
    script.write_text(
        f"import sys\nsys.stdout.write({QSTATUS_ALL!r})\nsys.stderr.write(repr(sys.argv[1:]))\n"
    )
    commands = {"qstatus": [sys.executable, str(script)]}
    server = LocalSSHServer(remote, ssh_keys, workdir, commands=commands)
    yield server
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"


@pytest.fixture
def spy(monkeypatch):
    """The argv, env and result of every command ``fetch_jobs`` runs."""
    runs = []
    real = cluster_jobs.run_command

    def run(argv, env, timeout_s):
        result = real(argv, env, timeout_s)
        runs.append((argv, env, result))
        return result

    monkeypatch.setattr(cluster_jobs, "run_command", run)
    return runs


def test_the_queue_by_key(server, spy):
    result = fetch_jobs(parse_config(server.config_data()))
    assert isinstance(result, JobsSnapshot), result
    assert [j.name for j in result.running] == ["Nd2Fe14B-4f-129", "hBN+Sm-1", "hBN+Eu-1"]
    assert len(result.waiting) == 2
    assert [(r.user, r.method, r.command) for r in server.log] == [
        (USER, "publickey", "qstatus -a")
    ]
    assert server.log[0].status == 0
    ((argv, _env, run),) = spy
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv
    assert run.stderr == "['-a']"  # the arguments of the command reach it


def test_the_queue_by_password_never_shows_it(server, spy, caplog, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    caplog.set_level(logging.DEBUG)
    config = parse_config(server.config_data(auth="password", password_env="LAIN_NO_PW"))
    result = fetch_jobs(config, password=PASSWORD)
    assert isinstance(result, JobsSnapshot), result
    assert {r.method for r in server.log} == {"password"}
    ((argv, env, _run),) = spy
    assert PASSWORD not in " ".join(argv) and env[SECRET_ENV] == PASSWORD
    assert "qstatus -a" in caplog.text and PASSWORD not in caplog.text


def test_a_wrong_password_is_a_refused_login(server, monkeypatch):
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    config = parse_config(server.config_data(auth="password", password_env="LAIN_NO_PW"))
    result = fetch_jobs(config, password="wrong")
    assert isinstance(result, JobsFailure) and result.auth and not result.connection
    assert server.log == [] and [a.accepted for a in server.attempts] == [False]


def test_a_command_the_cluster_does_not_have(server):
    result = fetch_jobs(parse_config(server.config_data(jobs_command="squeue -u lain-test")))
    assert isinstance(result, JobsFailure) and result.missing, result
    assert "squeue -u lain-test" in result.message
    assert [r.allowed for r in server.log] == [False]  # refused by the server, never run
