"""The ``prefix`` of a folder of the cluster (spec 70 R1): the pw.x inputs are told by their content,
copied up to 1 MB into a temporary folder of the cache, read and removed. The end-to-end test talks
only to the local ``tests/ssh_server.py``."""

import shutil
from pathlib import Path

from qe_studio.core.appdirs import cache_dir
from qe_studio.core.config import parse_config
from qe_studio.core.remote import inputs
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.inputs import fetch_prefixes, pw_prefixes
from qe_studio.core.remote.listing import NOT_FOUND
from qe_studio.core.sync.command import CommandResult
from qe_studio.core.sync.rsync import small_files_command

from conftest import FIXTURES, copy_fixture

PW = "&CONTROL\n  calculation = 'scf'\n{prefix}/\n&SYSTEM\n  ibrav = 2\n/\n&ELECTRONS\n/\n"


def pw_input(value: str | None) -> str:
    """A pw.x input whose ``prefix`` is ``value`` as written (quotes and all); None: no prefix."""
    return PW.format(prefix=f"  prefix = {value},\n" if value is not None else "")


def test_only_pw_inputs_count(tmp_path):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    assert pw_prefixes(folder) == ("al",)  # al.projwfc.in has prefix 'al' too, but is projwfc.x's
    only = tmp_path / "only"
    only.mkdir()
    shutil.copy(folder / "al.projwfc.in", only / "al.projwfc.in")
    assert pw_prefixes(only) == ()


def test_the_default_prefix_and_several_in_order(tmp_path):
    (tmp_path / "scf.in").write_text(pw_input(None))
    assert pw_prefixes(tmp_path) == ("pwscf",)
    (tmp_path / "relax").write_text(pw_input("'Zr'"))  # by content: any name
    (tmp_path / "bands.in").write_text(pw_input('"Al2O3 "'))
    (tmp_path / "nscf.in").write_text(pw_input("'Zr'"))
    assert pw_prefixes(tmp_path) == ("Al2O3", "Zr", "pwscf")


def test_outputs_and_scripts_do_not_count(tmp_path):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    for path in folder.glob("*.in"):
        path.unlink()
    (folder / "bands.qsub").write_text("#!/bin/bash\n#$ -N teste\nmpirun pw.x -in scf.in\n")
    assert pw_prefixes(folder) == ()


def test_the_command_copies_the_top_files_up_to_1_mb(tmp_path):
    config = parse_config({"cluster": {"host": "hpc.example", "user": "u"}})
    argv = small_files_command(config, "/home/u/runs/Al", tmp_path / "dest")
    assert argv[:4] == ["rsync", "-r", "--max-size=1M", "--exclude=*/"]
    assert "--no-h" in argv and "-e" in argv
    assert argv[-2:] == ["u@hpc.example:/home/u/runs/Al/", f"{tmp_path / 'dest'}/"]


def scratch_folders() -> list[str]:
    cache = cache_dir()
    return (
        sorted(p.name for p in cache.iterdir() if p.name.startswith("inputs-"))
        if cache.exists()
        else []
    )


def test_through_ssh_only_the_small_top_files_come(ssh_server, monkeypatch):
    server, remote = ssh_server
    folder = remote / "Al"
    (folder / "sub").mkdir(parents=True)
    shutil.copy(FIXTURES / "al_pdos_flat" / "al.scf.in", folder / "scf.in")
    (folder / "sub" / "inner.in").write_text(pw_input("'inner'"))
    (folder / "big.in").write_text(pw_input("'big'") + "!" * 2_000_000)
    seen: list[list[str]] = []
    real = inputs.pw_prefixes

    def spy(where):
        seen.append(sorted(p.name for p in where.iterdir()))
        return real(where)

    monkeypatch.setattr(inputs, "pw_prefixes", spy)
    config = parse_config(server.config_data())
    assert fetch_prefixes(config, str(folder)) == ("al",)
    assert seen == [["scf.in"]]  # no subfolder, nothing over 1 MB
    assert scratch_folders() == []  # the temporary folder is gone
    assert all(command.startswith("rsync --server --sender") for command in server.commands())

    missing = fetch_prefixes(config, str(remote / "nada"))
    assert missing == ActionFailure(NOT_FOUND, missing=True)
    assert scratch_folders() == []


def test_a_prefix_that_cannot_enter_a_command_is_refused(monkeypatch):
    monkeypatch.setattr(inputs, "local_version", lambda *_args: (3, 2, 7))

    def copy(argv, env, timeout_s):
        (Path(argv[-1]) / "scf.in").write_text(pw_input("'a b'"))
        return CommandResult(0, "", "")

    monkeypatch.setattr(inputs, "run_command", copy)
    config = parse_config({"cluster": {"host": "hpc.example", "user": "u"}})
    failure = fetch_prefixes(config, "/home/u/runs/Al")
    assert failure == ActionFailure("prefix não suportado para o arquivo de parada: a b.")
    assert scratch_folders() == []
