"""No secret in the log (spec 90 R8), proved on the **file**: with everything Lain can say (DEBUG),
a pull, the job list in a worker and an action on the cluster, by password. Only the local server
of ``tests/ssh_server.py`` answers."""

import shutil
import sys

import pytest

from qe_studio.core.app import logs
from qe_studio.core.appdirs import set_data_dir
from qe_studio.core.config import LoadedConfig, LogConfig, parse_config
from qe_studio.core.remote.actions import run_action
from qe_studio.core.remote.cluster_jobs import JobsSnapshot, fetch_jobs
from qe_studio.core.sync.controller import SyncController, SyncStatus
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.core.tasks import run_task

from jobs_helpers import EMPTY
from ssh_server import HOST_ALIAS, PASSWORD, USER, LocalSSHServer
from sync_helpers import run_sync, write


@pytest.fixture
def server(ssh_keys, tmp_path):
    """``(server, remote)``: rsync and an empty queue that also says something on stderr."""
    if shutil.which("rsync") is None or shutil.which("ssh") is None:
        pytest.skip("rsync and ssh are required")
    remote, workdir = tmp_path / "cluster", tmp_path / "ssh"
    remote.mkdir()
    workdir.mkdir()
    script = tmp_path / "qstatus.py"
    script.write_text(f"import sys\nsys.stdout.write({EMPTY!r})\nsys.stderr.write('qstatus ok')\n")
    commands = {"qstatus": [sys.executable, str(script)]}
    server = LocalSSHServer(remote, ssh_keys, workdir, commands=commands)
    yield server, remote
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"


def test_the_log_file_never_has_the_password(qtbot, server, log_session, tmp_path, monkeypatch):
    srv, remote = server
    monkeypatch.delenv("LAIN_NO_PW", raising=False)
    config = parse_config(srv.config_data(auth="password", password_env="LAIN_NO_PW"))
    data = tmp_path / "data"
    set_data_dir(data)
    log_session.start(verbose=True)
    assert log_session.apply_config(LogConfig(level="debug")) is None

    write(remote, "scf.out", "scf")
    controller = SyncController(config, password=PASSWORD)
    target = Endpoint(str(remote), HOST_ALIAS, USER)
    report, _plans = run_sync(qtbot, controller, tmp_path / "local", target)
    assert report.status is SyncStatus.DONE, report.error

    results = []
    handle = run_task(fetch_jobs, config, PASSWORD, on_done=results.append)
    assert handle.wait(30)
    qtbot.waitUntil(lambda: bool(results), timeout=5000)
    assert isinstance(results[0], JobsSnapshot), results

    result = run_action(config, "echo oi", PASSWORD)
    assert getattr(result, "code", None) == 0, result

    text = (data / "lain.log").read_text(encoding="utf-8")
    assert "sync: run " in text and "rsync" in text
    assert "task: " in text and "fetch_jobs done" in text
    assert "command: " in text and "qstatus" in text
    assert "cluster: action -> 0: oi" in text
    assert PASSWORD not in text


def test_the_session_lines_have_no_secret():
    config = parse_config(
        {
            "cluster": {
                "host": "hpc.test",
                "user": "ana",
                "auth": "password",
                "password": "sentinela-da-senha",
                "password_env": "SENTINELA_DA_VARIAVEL",
            },
            "jobs": {"myemail": "sentinela@email.test"},
        }
    )
    lines = "\n".join(logs.session_lines(LoadedConfig(config, None), "s.ini"))
    assert "ana@hpc.test" in lines
    for secret in ("sentinela-da-senha", "SENTINELA_DA_VARIAVEL", "sentinela@email.test"):
        assert secret not in lines
