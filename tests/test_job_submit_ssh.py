"""Submitting over a real ssh connection to the local paramiko server (spec 69 R5), never the cluster.

The server's ``qstatus`` prints an empty queue, ``chmod`` is the real one and ``qsub`` a Python
script that records the folder it ran in and the script it got, then answers as SGE does. The real
``ssh`` and ``rsync`` run with Lain's options, by key and by password (``SSH_ASKPASS``); the password
never reaches an argv or the log.
"""

import json
import logging
import shutil
import sys

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote import actions
from qe_studio.core.remote.submit import SubmitPlan, Submitted, plan_submit, submit
from qe_studio.core.sync.askpass import SECRET_ENV

from jobs_helpers import EMPTY
from ssh_server import PASSWORD, LocalSSHServer

QSUB = """\
import json, os, sys
with open({record!r}, "w") as f:
    json.dump({{"cwd": os.getcwd(), "args": sys.argv[1:]}}, f)
print('Your job 1 ("teste") has been submitted')
"""


@pytest.fixture
def server(ssh_keys, tmp_path):
    """``(server, folder, record)``: ``folder`` holds ``bands.qsub``; ``qsub`` writes ``record``."""
    if shutil.which("rsync") is None or shutil.which("ssh") is None:
        pytest.skip("rsync and ssh are required")
    remote, workdir = tmp_path / "cluster", tmp_path / "ssh"
    folder = remote / "ilita" / "Bands"
    folder.mkdir(parents=True)
    workdir.mkdir()
    script = folder / "bands.qsub"
    script.write_text("#!/bin/bash\n#$ -N teste\n#$ -cwd\n")
    script.chmod(0o644)
    record = tmp_path / "qsub.json"
    (tmp_path / "qsub.py").write_text(QSUB.format(record=str(record)))
    (tmp_path / "qstatus.py").write_text(f"import sys\nsys.stdout.write({EMPTY!r})\n")
    commands = {
        "qstatus": [sys.executable, str(tmp_path / "qstatus.py")],
        "chmod": ["chmod"],
        "qsub": [sys.executable, str(tmp_path / "qsub.py")],
    }
    server = LocalSSHServer(remote, ssh_keys, workdir, commands=commands)
    yield server, folder, record
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"


@pytest.fixture
def spy(monkeypatch):
    """The argv and env of every command ``run_action`` runs."""
    runs = []
    real = actions.run_command

    def run(argv, env, timeout_s):
        runs.append((argv, env))
        return real(argv, env, timeout_s)

    monkeypatch.setattr(actions, "run_command", run)
    return runs


def submitted(config, folder, password=None):
    plan = plan_submit(config, str(folder), "bands.qsub", password)
    assert isinstance(plan, SubmitPlan), plan
    assert plan.exit_files == ()
    return plan, submit(config, plan, password)


def test_a_submission_by_key_runs_in_the_script_folder(server, spy):
    srv, folder, record = server
    plan, result = submitted(parse_config(srv.config_data()), folder)
    assert result == Submitted("1", "teste")
    assert json.loads(record.read_text()) == {"cwd": str(folder.resolve()), "args": ["bands.qsub"]}
    assert (folder / "bands.qsub").stat().st_mode & 0o111 == 0o111  # chmod a+x ran
    assert plan.line in srv.commands()
    ((argv, _env),) = spy
    assert argv[-1] == plan.line and "StrictHostKeyChecking=yes" in argv


def test_a_submission_by_password_never_shows_it(server, spy, caplog, monkeypatch):
    srv, folder, record = server
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    caplog.set_level(logging.DEBUG)
    config = parse_config(srv.config_data(auth="password", password_env="LAIN_NO_PW"))
    plan, result = submitted(config, folder, PASSWORD)
    assert result == Submitted("1", "teste") and record.exists()
    assert {r.method for r in srv.log} == {"password"}
    ((argv, env),) = spy
    assert PASSWORD not in " ".join(argv) and env[SECRET_ENV] == PASSWORD
    assert plan.line in caplog.text and PASSWORD not in caplog.text
