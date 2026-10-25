"""Cancelling over a real ssh connection to the local paramiko server (spec 70 R2.3), never the cluster.

The server's ``qstatus`` prints what the test writes in ``queue.txt``, ``touch`` is the real one and
``qdel`` a Python script that records the IDs it gets. The real ``ssh`` and ``rsync`` run with Lain's
options: the folder is listed, the inputs copied and read, the stop file created in the served folder.
"""

import shutil
import sys

import pytest

from qe_studio.core.cluster_jobs import parse_qstatus
from qe_studio.core.config import parse_config
from qe_studio.core.remote.job_cancel import (
    Done,
    Refused,
    StopPlan,
    delete_waiting,
    plan_stop,
    stop,
)

from conftest import FIXTURES
from ssh_server import USER, LocalSSHServer

QDEL = """\
import sys
with open({record!r}, "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
print("{user} has registered the job " + sys.argv[1] + " for deletion")
"""
RUNNING = f"  7 16 teste {USER} 10/24/2026 09:00:00 physica.q\n"
WAITING = f"  8 16 espera {USER} 10/24/2026 10:00:00\n"


def queue(running: str = "", waiting: str = "") -> str:
    return f"Running jobs:\n{running}\nWaiting jobs:\n{waiting}"


@pytest.fixture
def server(ssh_keys, tmp_path):
    """``(server, folder, queue_file, record)``: ``folder`` holds ``al.scf.in`` and ``teste.o7``."""
    if shutil.which("rsync") is None or shutil.which("ssh") is None:
        pytest.skip("rsync and ssh are required")
    remote, workdir = tmp_path / "cluster", tmp_path / "ssh"
    folder = remote / "ilita" / "Al"
    folder.mkdir(parents=True)
    workdir.mkdir()
    shutil.copy(FIXTURES / "al_pdos_flat" / "al.scf.in", folder / "al.scf.in")
    (folder / "teste.o7").write_text("")
    queue_file, record = tmp_path / "queue.txt", tmp_path / "qdel.txt"
    queue_file.write_text(queue(RUNNING, WAITING))
    (tmp_path / "qstatus.py").write_text(
        f"import sys\nsys.stdout.write(open({str(queue_file)!r}).read())\n"
    )
    (tmp_path / "qdel.py").write_text(QDEL.format(record=str(record), user=USER))
    commands = {
        "qstatus": [sys.executable, str(tmp_path / "qstatus.py")],
        "touch": ["touch"],
        "qdel": [sys.executable, str(tmp_path / "qdel.py")],
    }
    server = LocalSSHServer(remote, ssh_keys, workdir, commands=commands)
    yield server, folder, queue_file, record
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"


def test_a_running_job_gets_its_stop_file(server):
    srv, folder, _queue, _record = server
    config = parse_config(srv.config_data())
    plan = plan_stop(config, str(folder))
    assert isinstance(plan, StopPlan), plan
    assert [job.job_id for job in plan.jobs] == ["7"] and plan.prefixes == ("al",)
    assert not (folder / "al.EXIT").exists()  # planning changes nothing
    assert stop(config, plan) == Done(
        "Pedido de parada criado: al.EXIT. O pw.x para na próxima verificação."
    )
    assert (folder / "al.EXIT").read_bytes() == b""
    assert plan.line in srv.commands()


def test_a_job_that_ended_gets_no_stop_file(server):
    srv, folder, queue_file, _record = server
    config = parse_config(srv.config_data())
    plan = plan_stop(config, str(folder))
    assert isinstance(plan, StopPlan)
    queue_file.write_text(queue(waiting=WAITING))  # it ended while the dialog was open
    assert isinstance(stop(config, plan), Refused)
    assert not (folder / "al.EXIT").exists()
    assert not any(command.startswith("touch") for command in srv.commands())


def test_qdel_gets_the_id_of_a_waiting_job_only(server):
    srv, _folder, queue_file, record = server
    config = parse_config(srv.config_data())
    waiting = parse_qstatus(queue(RUNNING, WAITING)).waiting[0]
    assert delete_waiting(config, waiting) == Done("Job 8 (espera) cancelado com qdel.")
    assert record.read_text() == "8\n"

    record.unlink()
    started = f"  8 16 espera {USER} 10/24/2026 11:00:00 physica.q\n"
    queue_file.write_text(queue(RUNNING + started))  # it started before the click
    assert isinstance(delete_waiting(config, waiting), Refused)
    assert not record.exists()  # qdel never ran
