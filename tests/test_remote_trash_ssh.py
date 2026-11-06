"""Moving to the trash over a real ssh connection to the local paramiko server (spec 84 R1.6), never the
cluster.

The server's ``qstatus`` prints what the test writes in ``queue.txt``; ``mkdir``, ``test`` and ``mv`` are
one Python script (``FS``) that acts only inside the served folder and whose ``mv`` refuses a target
that exists. The real ``ssh`` and ``rsync`` run with Lain's options: the folders are listed, the queue
asked and the line run from the root, as on the cluster.
"""

import shutil
import sys
from datetime import datetime

import pytest

from qe_studio.core.config import parse_config
from qe_studio.core.remote.trash import TrashBlocked, TrashDone, TrashPlan, plan_trash, run_trash

from ssh_server import USER, LocalSSHServer

NOW = datetime(2026, 10, 30, 14, 2, 11)
STAMP = "2026-10-30_14-02-11"
FS = """\
import os, sys
from pathlib import Path

ROOT = Path({root!r}).resolve()


def inside(arg):
    path = (Path.cwd() / arg).resolve()
    if not path.is_relative_to(ROOT):
        sys.exit("fs: outside the served folder: " + arg)
    return path


op, args = sys.argv[1], sys.argv[2:]
if op == "mkdir" and args[:1] == ["-p"]:
    for arg in args[1:]:
        inside(arg).mkdir(parents=True, exist_ok=True)
elif op == "test" and args[:2] == ["!", "-e"] and len(args) == 3:
    sys.exit(1 if os.path.lexists(inside(args[2])) else 0)
elif op == "mv" and len(args) == 2:
    source, target = inside(args[0]), inside(args[1])
    if os.path.lexists(target):
        sys.exit("mv: target exists: " + args[1])
    source.rename(target)
else:
    sys.exit("fs: not supported: " + " ".join(sys.argv[1:]))
"""


def queue(running: str = "") -> str:
    return f"Running jobs:\n{running}\nWaiting jobs:\n"


@pytest.fixture
def server(ssh_keys, tmp_path):
    """``(server, root, queue_file)``: ``root/projeto`` holds ``PDOS/`` (with a file and a subfolder)
    and ``scf.in``; the queue has no job."""
    if shutil.which("rsync") is None or shutil.which("ssh") is None:
        pytest.skip("rsync and ssh are required")
    root, workdir = tmp_path / "cluster", tmp_path / "ssh"
    pdos = root / "projeto" / "PDOS"
    (pdos / "orbitals").mkdir(parents=True)
    (pdos / "al.pdos_tot").write_text("pdos")
    (pdos / "orbitals" / "al.pdos_atm#1(Al)_wfc#1(s)").write_text("s")
    (root / "projeto" / "scf.in").write_text("&control /")
    workdir.mkdir()
    queue_file = tmp_path / "queue.txt"
    queue_file.write_text(queue())
    (tmp_path / "qstatus.py").write_text(
        f"import sys\nsys.stdout.write(open({str(queue_file)!r}).read())\n"
    )
    (tmp_path / "fs.py").write_text(FS.format(root=str(root)))
    fs = [sys.executable, str(tmp_path / "fs.py")]
    commands = {
        "qstatus": [sys.executable, str(tmp_path / "qstatus.py")],
        "mkdir": [*fs, "mkdir"],
        "test": [*fs, "test"],
        "mv": [*fs, "mv"],
    }
    server = LocalSSHServer(root, ssh_keys, workdir, commands=commands)
    yield server, root, queue_file
    server.close()
    assert not (alive := server.alive_threads()), f"SSH server threads left running: {alive}"


def moves(srv) -> list[str]:
    return [command for command in srv.commands() if " mv " in command]


def test_a_folder_goes_to_the_trash_with_its_content(server):
    srv, root, _queue = server
    config = parse_config(srv.config_data())
    plan = plan_trash(config, [(str(root / "projeto" / "PDOS"), True)], now=NOW)
    assert isinstance(plan, TrashPlan), plan
    assert (root / "projeto" / "PDOS").is_dir() and not (root / "trash").exists()  # nothing yet
    assert moves(srv) == []
    assert run_trash(config, plan) == TrashDone(plan.moves)
    target = root / "trash" / "projeto" / f"PDOS_{STAMP}"
    assert (target / "al.pdos_tot").read_text() == "pdos"
    assert (target / "orbitals" / "al.pdos_atm#1(Al)_wfc#1(s)").read_text() == "s"
    assert not (root / "projeto" / "PDOS").exists()
    assert plan.line in srv.commands()


def test_a_file_goes_to_the_trash_with_the_date_before_its_extension(server):
    srv, root, _queue = server
    config = parse_config(srv.config_data())
    plan = plan_trash(config, [(str(root / "projeto" / "scf.in"), False)], now=NOW)
    assert isinstance(plan, TrashPlan), plan
    assert isinstance(run_trash(config, plan), TrashDone)
    assert (root / "trash" / "projeto" / f"scf_{STAMP}.in").read_text() == "&control /"
    assert not (root / "projeto" / "scf.in").exists()


def test_a_target_that_exists_stops_the_line_and_nothing_is_overwritten(server):
    srv, root, _queue = server
    config = parse_config(srv.config_data())
    taken = root / "trash" / "projeto" / f"scf_{STAMP}.in"
    taken.parent.mkdir(parents=True)
    taken.write_text("deleted before")
    items = [(str(root / "projeto" / "scf.in"), False), (str(root / "projeto" / "PDOS"), True)]
    plan = plan_trash(config, items, now=NOW)
    assert isinstance(plan, TrashPlan), plan
    answer = run_trash(config, plan)
    assert not isinstance(answer, TrashDone | TrashBlocked)
    assert answer.message == (
        f"Já existe trash/projeto/scf_{STAMP}.in no cluster: nada foi sobrescrito."
    )
    assert taken.read_text() == "deleted before"
    assert (root / "projeto" / "scf.in").exists() and (root / "projeto" / "PDOS").is_dir()


def test_a_running_job_in_the_folder_blocks_before_any_move(server):
    srv, root, queue_file = server
    config = parse_config(srv.config_data())
    (root / "projeto" / "PDOS" / "PDOS-Al.o7").write_text("")
    queue_file.write_text(queue(f"  7 16 PDOS-Al {USER} 10/30/2026 09:00:00 physica.q\n"))
    plan = plan_trash(config, [(str(root / "projeto" / "PDOS"), True)], now=NOW)
    assert plan == TrashBlocked(
        "Há um job seu em execução em projeto/PDOS (7): cancele-o antes de apagar."
    )
    assert moves(srv) == [] and not (root / "trash").exists()
    assert (root / "projeto" / "PDOS").is_dir()


def test_a_running_job_deep_in_a_folder_deleted_blocks_before_any_move(server):
    """Its output is two folders down: the folder deleted is listed whole with the real rsync."""
    srv, root, queue_file = server
    config = parse_config(srv.config_data())
    (root / "projeto" / "PDOS" / "orbitals" / "PDOS-Al.o7").write_text("")
    queue_file.write_text(queue(f"  7 16 PDOS-Al {USER} 10/30/2026 09:00:00 physica.q\n"))
    plan = plan_trash(config, [(str(root / "projeto"), True)], now=NOW)
    assert plan == TrashBlocked(
        "Há um job seu em execução em projeto/PDOS/orbitals (7): cancele-o antes de apagar."
    )
    assert moves(srv) == [] and (root / "projeto" / "PDOS" / "orbitals").is_dir()
    queue_file.write_text(queue(f"  8 16 PDOS-Al {USER} 10/30/2026 09:00:00 physica.q\n"))
    assert isinstance(plan_trash(config, [(str(root / "projeto"), True)], now=NOW), TrashPlan)
