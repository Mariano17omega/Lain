"""Spec 25 R7: the new folder, never over anything that exists (named as spec 28 R1 says)."""

import builtins
import os

import pytest

from qe_studio.core.calc_create.types import REGISTRY, by_id
from qe_studio.core.calc_create.types.base import CalcPlan, PlannedFile
from qe_studio.core.calc_create.writer import (
    CreateError,
    create_folder,
    files_to_write,
    folder_name,
    preview_name,
    validate_suffix,
    validate_target,
)

from calc_helpers import AL_PATH, JOBS, al

BANDAS = by_id("bandas")


def bands_plan():
    plan = BANDAS.plan(al(), {"kpath": AL_PATH}, JOBS)
    assert plan.ok
    return plan


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_creates_the_folder_and_numbers_the_next_ones(tmp_path):
    (tmp_path / "other").mkdir()
    plan = bands_plan()
    assert preview_name(tmp_path, BANDAS, "Al") == "Bands_Al"
    first = create_folder(tmp_path, BANDAS, "Al", plan)
    assert first.folder == tmp_path / "Bands_Al" and first.renamed_from is None
    assert [p.name for p in first.files] == [f.name for f in plan.files]
    for planned in plan.files:
        assert (first.folder / planned.name).read_text() == planned.text
    assert preview_name(tmp_path, BANDAS, "Al") == "Bands_Al_1"
    second = create_folder(tmp_path, BANDAS, "Al", plan)
    third = create_folder(tmp_path, BANDAS, "Al", plan)
    assert (second.folder.name, third.folder.name) == ("Bands_Al_1", "Bands_Al_2")
    assert second.renamed_from == "Bands_Al"
    top = sorted(p.name for p in tmp_path.iterdir())
    assert top == ["Bands_Al", "Bands_Al_1", "Bands_Al_2", "other"]
    assert tree(tmp_path / "other") == []


def test_without_a_name_the_folder_is_the_prefix(tmp_path):
    plan = bands_plan()
    assert folder_name(BANDAS, "") == folder_name(BANDAS, "  ") == "Bands"
    assert preview_name(tmp_path, BANDAS, "") == "Bands"
    assert create_folder(tmp_path, BANDAS, "", plan).folder.name == "Bands"
    assert preview_name(tmp_path, BANDAS, "") == "Bands_1"
    second = create_folder(tmp_path, BANDAS, " ", plan)
    assert (second.folder.name, second.renamed_from) == ("Bands_1", "Bands")
    names = [folder_name(t, "") for t in REGISTRY]
    assert names == ["SCF", "Relax", "VC-Relax", "Bands", "PDOS"]


def test_a_file_in_the_way_is_not_touched(tmp_path):
    (tmp_path / "Bands_Al").write_text("not a folder")
    created = create_folder(tmp_path, BANDAS, "Al", bands_plan())
    assert created.folder.name == "Bands_Al_1"
    assert (tmp_path / "Bands_Al").read_text() == "not a folder"


def test_notes_only_with_text(tmp_path):
    plan = bands_plan()
    assert [f.name for f in files_to_write(plan, "  \n")] == [f.name for f in plan.files]
    blank = create_folder(tmp_path, BANDAS, "a", plan, "  \n")
    assert not (blank.folder / "descricao.md").exists()
    noted = create_folder(tmp_path, BANDAS, "b", plan, "Bandas do Al\ncom 12 pontos")
    assert (noted.folder / "descricao.md").read_text() == "Bandas do Al\ncom 12 pontos\n"
    assert noted.files[-1].name == "descricao.md"


def test_files_are_created_exclusively(tmp_path, monkeypatch):
    modes = []
    real_open = builtins.open

    def spy(path, mode="r", *args, **kwargs):
        modes.append(mode)
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    create_folder(tmp_path, BANDAS, "Al", bands_plan(), "nota")
    assert modes == ["x"] * 5


def test_a_failed_write_removes_only_what_it_created(tmp_path, monkeypatch):
    (tmp_path / "keep.txt").write_text("mine")
    real_open = builtins.open
    calls = []

    def failing(path, mode="r", *args, **kwargs):
        if mode == "x":
            calls.append(path)
            if len(calls) == 3:
                raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", failing)
    with pytest.raises(CreateError, match="Não foi possível gravar bands.in"):
        create_folder(tmp_path, BANDAS, "Al", bands_plan())
    assert tree(tmp_path) == ["keep.txt"]


def test_bad_plans_and_targets_create_nothing(tmp_path):
    with pytest.raises(CreateError, match="Preencha"):
        create_folder(tmp_path, BANDAS, "Al", BANDAS.plan(al(), {}, JOBS))
    sneaky = CalcPlan((PlannedFile("../evil.in", "pw_input", "x", "x"),))
    with pytest.raises(CreateError, match="inválido"):
        create_folder(tmp_path, BANDAS, "Al", sneaky)
    twice = CalcPlan((PlannedFile("a.in", "pw_input", "x", "x"),) * 2)
    with pytest.raises(CreateError, match="repetido"):
        create_folder(tmp_path, BANDAS, "Al", twice)
    with pytest.raises(CreateError, match="Use só letras"):
        create_folder(tmp_path, BANDAS, "a/b", bands_plan())
    assert tree(tmp_path) == []


@pytest.mark.parametrize(
    "suffix, message",
    [
        ("a/b", "Use só letras"),
        (".", "Use só letras"),
        ("Alumínio", "Use só letras"),
        ("..", "Use só letras"),
        ("a b", "Use só letras"),
    ],
)
def test_validate_target_refuses_bad_names(tmp_path, suffix, message):
    assert any(message in problem for problem in validate_target(tmp_path, suffix))


def test_validate_target_checks_the_parent(tmp_path):
    assert validate_target(tmp_path, "Al_v2.1-x") == []
    assert validate_target(tmp_path, "") == validate_suffix("") == []  # the name is optional
    assert any("não existe" in p for p in validate_target(tmp_path / "missing", "Al"))
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("running as root: permissions are not enforced")
        assert any("Sem permissão" in p for p in validate_target(locked, "Al"))
    finally:
        locked.chmod(0o700)
