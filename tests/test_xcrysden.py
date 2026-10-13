"""Spec 45 R2: which XCrySDen option reads a file, where the program is, and the argv (no Qt)."""

import os
from pathlib import Path

import pytest

from qe_studio.core.sniff import FileKind
from qe_studio.core.xcrysden import NOT_SET, command, locate, option_for


def make_script(path: Path, mode: int = 0o755) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(mode)
    return path


def test_only_pw_inputs_and_outputs_have_an_option():
    options = {kind: option_for(kind) for kind in FileKind}
    assert options[FileKind.PW_IN] == "--pwi"
    assert options[FileKind.PW_OUT] == "--pwo"
    others = {kind for kind, option in options.items() if option is None}
    assert others == set(FileKind) - {FileKind.PW_IN, FileKind.PW_OUT}


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_nothing_configured_says_what_to_set(configured):
    found = locate(configured)
    assert found.executable is None and found.problem == NOT_SET
    assert "paths.xcrysden_path" in found.problem


def test_a_folder_with_the_script_gives_the_script(tmp_path):
    script = make_script(tmp_path / "xcrysden-1.6.2-bin-shared" / "xcrysden")
    found = locate(str(script.parent))
    assert found == (script, "")


def test_the_script_itself_is_accepted(tmp_path):
    script = make_script(tmp_path / "my-xcrysden")  # any name: the user pointed at it
    assert locate(str(script)) == (script, "")


def test_a_missing_path_is_not_found(tmp_path):
    missing = tmp_path / "nowhere"
    found = locate(str(missing))
    assert found.executable is None
    assert found.problem == f"XCrysDen não encontrado: {missing}."


def test_a_folder_without_the_script(tmp_path):
    folder = tmp_path / "xcrysden-dir"
    folder.mkdir()
    (folder / "README").write_text("not it", encoding="utf-8")
    found = locate(str(folder))
    assert found.executable is None
    assert found.problem == f"Não há o executável xcrysden em {folder}."


@pytest.mark.skipif(os.name == "nt", reason="no execute bit")
def test_a_file_without_the_execute_bit(tmp_path):
    script = make_script(tmp_path / "xcrysden", mode=0o644)
    for configured in (script, script.parent):  # the file, and the folder that holds it
        found = locate(str(configured))
        assert found.executable is None
        assert found.problem == f"{script} não é executável."


def test_the_command_is_argv_with_the_absolute_path(tmp_path):
    script = tmp_path / "xcrysden"
    spaced = tmp_path / "my runs" / "scf 1.in"
    assert command(script, "--pwi", spaced) == [str(script), "--pwi", str(spaced)]


def test_a_relative_path_becomes_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    argv = command(Path("/opt/xcrysden"), "--pwo", Path("runs/scf.out"))
    assert argv == ["/opt/xcrysden", "--pwo", str(tmp_path / "runs" / "scf.out")]
