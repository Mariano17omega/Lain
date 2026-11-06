"""Small files of a folder of the cluster (spec 70 R1, spec 71 R1–R3): the ``prefix`` of the SCF, relax
and vc-relax inputs of pw.x and the job name of a script, told by their content, copied up to 1 MB
into a temporary folder of the cache, read and removed. rsync's codes 23 and 24 keep what arrived.
The end-to-end tests talk only to the local ``tests/ssh_server.py``."""

import shutil
from pathlib import Path

import pytest

from qe_studio.core.appdirs import cache_dir
from qe_studio.core.config import parse_config
from qe_studio.core.remote import inputs
from qe_studio.core.remote.actions import ActionFailure
from qe_studio.core.remote.inputs import (
    StopSource,
    fetch_job_name,
    fetch_stop_sources,
    stop_sources,
)
from qe_studio.core.remote.listing import NOT_FOUND
from qe_studio.core.sync.command import CommandResult
from qe_studio.core.sync.rsync import small_files_command

from conftest import FIXTURES, copy_fixture

PW = "&CONTROL\n{calculation}{prefix}/\n&SYSTEM\n  ibrav = 2\n/\n&ELECTRONS\n/\n"
CONFIG = {"cluster": {"host": "hpc.example", "user": "u"}}
SCRIPT = '#!/bin/bash\n#$ -N "BD010o1"\n#$ -cwd\nmpirun pw.x -i scf.in > scf.out\n'
VANISHED = 'file has vanished: "/home/u/runs/Al/al.mix1"\n'


def pw_input(value: str | None, calculation: str | None = "'scf'") -> str:
    """A pw.x input whose ``prefix`` is ``value`` as written (quotes and all); None: no prefix.
    ``calculation`` likewise; None: no ``calculation`` (pw.x runs an SCF)."""
    return PW.format(
        calculation=f"  calculation = {calculation},\n" if calculation is not None else "",
        prefix=f"  prefix = {value},\n" if value is not None else "",
    )


def source(prefix: str, *names: str) -> StopSource:
    return StopSource(prefix, names)


# -- which inputs name the stop file (R2) ---------------------------------------------------------
def test_only_the_scf_input_of_pw_counts(tmp_path):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    # al.nscf.in (nscf) and al.projwfc.in (projwfc.x) have prefix 'al' too, but do not count
    assert stop_sources(folder) == (source("al", "al.scf.in"),)
    only = tmp_path / "only"
    only.mkdir()
    shutil.copy(folder / "al.nscf.in", only / "al.nscf.in")
    shutil.copy(folder / "al.projwfc.in", only / "al.projwfc.in")
    assert stop_sources(only) == ()


def test_bands_runs_of_pw_and_bands_x_do_not_count(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)  # al.scf.in, al.band.in (bands), bands.in (bands.x)
    assert stop_sources(folder) == (source("al", "al.scf.in"),)


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("si_relax", source("silicon", "si.rel.in")),
        ("kao_vc_relax", source("kaolinite", "vc-relax.in")),
    ],
)
def test_relax_and_vc_relax_count(tmp_path, fixture, expected):
    assert stop_sources(copy_fixture(fixture, tmp_path)) == (expected,)


def test_the_default_calculation_and_prefix(tmp_path):
    (tmp_path / "scf.in").write_text(pw_input(None, calculation=None))
    assert stop_sources(tmp_path) == (source("pwscf", "scf.in"),)


def test_one_file_per_prefix_with_the_inputs_that_set_it(tmp_path):
    (tmp_path / "ecut30.in").write_text(pw_input("'e30'"))
    (tmp_path / "ecut40.in").write_text(pw_input("'e40'"))
    (tmp_path / "relax").write_text(pw_input("'Zr'", "'relax'"))  # by content: any name
    (tmp_path / "scf.in").write_text(pw_input('"Zr "', '"SCF"'))
    (tmp_path / "vc.in").write_text(pw_input("'Al2O3'", "'vc-relax'"))
    (tmp_path / "nscf.in").write_text(pw_input("'nscf_only'", "'nscf'"))
    (tmp_path / "bands.in").write_text(pw_input("'bands_only'", "'bands'"))
    (tmp_path / "md.in").write_text(pw_input("'md_only'", "'md'"))
    assert stop_sources(tmp_path) == (
        source("Al2O3", "vc.in"),
        source("Zr", "relax", "scf.in"),
        source("e30", "ecut30.in"),
        source("e40", "ecut40.in"),
    )


def test_outputs_and_scripts_do_not_count(tmp_path):
    folder = copy_fixture("al_pdos_flat", tmp_path)
    for path in folder.glob("*.in"):
        path.unlink()
    (folder / "bands.qsub").write_text("#!/bin/bash\n#$ -N teste\nmpirun pw.x -in scf.in\n")
    assert stop_sources(folder) == ()


# -- the copy ------------------------------------------------------------------------------------
def test_the_command_copies_the_top_files_up_to_1_mb(tmp_path):
    config = parse_config(CONFIG)
    argv = small_files_command(config, "/home/u/runs/Al", tmp_path / "dest")
    assert argv[:4] == ["rsync", "-r", "--max-size=1M", "--exclude=*/"]
    assert "--no-h" in argv and "-e" in argv and "--exclude=*" not in argv
    assert argv[-2:] == ["u@hpc.example:/home/u/runs/Al/", f"{tmp_path / 'dest'}/"]


def test_the_command_for_one_file_includes_it_then_excludes_the_rest(tmp_path):
    config = parse_config(CONFIG)
    argv = small_files_command(config, "/home/u/runs/Al", tmp_path / "dest", only="bands.qsub")
    assert argv[:6] == [
        "rsync",
        "-r",
        "--max-size=1M",
        "--exclude=*/",
        "--include=bands.qsub",
        "--exclude=*",
    ]
    assert argv[-2:] == ["u@hpc.example:/home/u/runs/Al/", f"{tmp_path / 'dest'}/"]


def scratch_folders() -> list[str]:
    cache = cache_dir()
    return (
        sorted(p.name for p in cache.iterdir() if p.name.startswith("inputs-"))
        if cache.exists()
        else []
    )


def fake_rsync(monkeypatch, code: int, stderr: str = "", files: dict[str, str] | None = None):
    """rsync answers ``code`` after writing ``files`` (name → text) into its destination."""
    monkeypatch.setattr(inputs, "local_version", lambda *_args: (3, 2, 7))

    def copy(argv, env, timeout_s):
        for name, text in (files or {}).items():
            (Path(argv[-1]) / name).write_text(text)
        return CommandResult(code, "", stderr)

    monkeypatch.setattr(inputs, "run_command", copy)


def test_through_ssh_only_the_small_top_files_come(ssh_server, monkeypatch):
    server, remote = ssh_server
    folder = remote / "Al"
    (folder / "sub").mkdir(parents=True)
    shutil.copy(FIXTURES / "al_pdos_flat" / "al.scf.in", folder / "scf.in")
    (folder / "sub" / "inner.in").write_text(pw_input("'inner'"))
    (folder / "big.in").write_text(pw_input("'big'") + "!" * 2_000_000)
    seen: list[list[str]] = []
    real = inputs.stop_sources

    def spy(where):
        seen.append(sorted(p.name for p in where.iterdir()))
        return real(where)

    monkeypatch.setattr(inputs, "stop_sources", spy)
    config = parse_config(server.config_data())
    assert fetch_stop_sources(config, str(folder)) == (source("al", "scf.in"),)
    assert seen == [["scf.in"]]  # no subfolder, nothing over 1 MB
    assert scratch_folders() == []  # the temporary folder is gone
    assert all(command.startswith("rsync --server --sender") for command in server.commands())

    missing = fetch_stop_sources(config, str(remote / "nada"))
    assert missing == ActionFailure(NOT_FOUND, missing=True)
    assert scratch_folders() == []


def test_a_prefix_that_cannot_enter_a_command_is_refused(monkeypatch):
    fake_rsync(monkeypatch, 0, files={"scf.in": pw_input("'a b'")})
    failure = fetch_stop_sources(parse_config(CONFIG), "/home/u/runs/Al")
    assert failure == ActionFailure("prefix não suportado para o arquivo de parada: a b.")
    assert scratch_folders() == []


# -- rsync's partial copies (R1) -----------------------------------------------------------------
@pytest.mark.parametrize("code", [23, 24])
def test_a_partial_copy_that_brought_an_input_is_read(monkeypatch, code):
    fake_rsync(monkeypatch, code, VANISHED, files={"scf.in": pw_input("'al'")})
    assert fetch_stop_sources(parse_config(CONFIG), "/home/u/runs/Al") == (source("al", "scf.in"),)
    assert scratch_folders() == []


def test_a_partial_copy_without_an_input_still_fails(monkeypatch):
    fake_rsync(monkeypatch, 24, VANISHED, files={"nscf.in": pw_input("'al'", "'nscf'")})
    failure = fetch_stop_sources(parse_config(CONFIG), "/home/u/runs/Al")
    assert isinstance(failure, ActionFailure) and "24" in failure.message


def test_a_missing_folder_with_code_23_is_still_not_found(monkeypatch):
    stderr = 'rsync: [sender] change_dir "/home/u/runs/Al" failed: No such file or directory (2)\n'
    fake_rsync(monkeypatch, 23, stderr)
    failure = fetch_stop_sources(parse_config(CONFIG), "/home/u/runs/Al")
    assert failure == ActionFailure(NOT_FOUND, missing=True)


def test_other_codes_fail_even_with_an_input(monkeypatch):
    fake_rsync(
        monkeypatch,
        12,
        "rsync error: error in rsync protocol data stream\n",
        {"scf.in": pw_input("'al'")},
    )
    failure = fetch_stop_sources(parse_config(CONFIG), "/home/u/runs/Al")
    assert isinstance(failure, ActionFailure) and "12" in failure.message


# -- the job name of a script (R3) ---------------------------------------------------------------
def test_the_job_name_comes_from_the_script(monkeypatch):
    fake_rsync(monkeypatch, 0, files={"bands.qsub": SCRIPT})
    assert fetch_job_name(parse_config(CONFIG), "/home/u/runs/Al", "bands.qsub") == "BD010o1"
    fake_rsync(monkeypatch, 24, VANISHED, files={"run.qsub": "#!/bin/bash\npw.x\n"})
    assert fetch_job_name(parse_config(CONFIG), "/home/u/runs/Al", "run.qsub") == "run.qsub"
    assert scratch_folders() == []


def test_a_script_that_did_not_come_is_a_failure(monkeypatch):
    fake_rsync(monkeypatch, 0)
    failure = fetch_job_name(parse_config(CONFIG), "/home/u/runs/Al", "big.qsub")
    assert failure == ActionFailure(
        "O script big.qsub não foi encontrado na pasta, ou passa de 1 MB."
    )


def test_through_ssh_only_the_script_comes(ssh_server):
    server, remote = ssh_server
    folder = remote / "Bands"
    folder.mkdir()
    (folder / "bands.qsub").write_text(SCRIPT)
    (folder / "scf.in").write_text(pw_input("'al'"))
    config = parse_config(server.config_data())
    assert fetch_job_name(config, str(folder), "bands.qsub") == "BD010o1"
    assert scratch_folders() == []
