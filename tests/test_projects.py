"""core/project/projects (spec 31 R1): the project list, the owner of a path, the name check, the
folder."""

import os
from pathlib import Path

import pytest

from qe_studio.core.project.projects import (
    ProjectError,
    create_project,
    list_projects,
    project_of,
    root_name_error,
    validate_project_name,
)


def make(root: Path, *folders: str) -> Path:
    for folder in folders:
        (root / folder).mkdir(parents=True)
    return root


def names(root: Path, hidden: list[str] | None = None) -> list[str]:
    return [project.name for project in list_projects(root, hidden or [])]


def test_only_first_level_folders_are_projects(tmp_path):
    make(tmp_path, "ilita/Analise_1/Bandas", "outro")
    (tmp_path / "solto.txt").write_text("a loose file")
    projects = list_projects(tmp_path, [])
    assert [p.name for p in projects] == ["ilita", "outro"]
    assert projects[0].path == tmp_path / "ilita"


def test_hidden_dotted_exports_and_links_are_not_projects(tmp_path):
    make(tmp_path, "ilita", ".git", "tmp", "run.save", "plots", "real")
    os.symlink(tmp_path / "real", tmp_path / "link", target_is_directory=True)
    assert names(tmp_path, ["tmp", "*.save"]) == ["ilita", "real"]


def test_the_mirror_of_the_cluster_trash_is_not_a_project(tmp_path):
    """Spec 84: a "Baixar" of a trash item makes ``<root>/trash``; as a project, "Sincronizar projeto"
    would pull the whole trash. A project's own ``trash`` changes nothing."""
    make(tmp_path, "ilita/trash", "trash/ilita/PDOS_2026-10-30_14-02-11")
    assert names(tmp_path) == ["ilita"]


def test_the_order_ignores_case_and_accents(tmp_path):
    make(tmp_path, "banana", "Árvore", "abacaxi", "Zebra", "arara")
    assert names(tmp_path) == ["abacaxi", "arara", "Árvore", "banana", "Zebra"]


def test_an_unreadable_root_has_no_projects(tmp_path):
    assert list_projects(tmp_path / "gone", []) == []
    (tmp_path / "file").write_text("x")
    assert list_projects(tmp_path / "file", []) == []


def test_a_cancelled_scan_returns_what_it_has(tmp_path):
    make(tmp_path, "a", "b", "c")
    assert list_projects(tmp_path, [], cancelled=lambda: True) == []


def test_project_of_is_the_first_component_below_the_root(tmp_path):
    assert project_of(tmp_path, tmp_path) is None
    assert project_of(tmp_path / "ilita", tmp_path) == "ilita"
    assert project_of(tmp_path / "ilita" / "Analise_1" / "Bandas", tmp_path) == "ilita"
    assert project_of(Path("/elsewhere/ilita"), tmp_path) is None
    assert project_of(tmp_path.parent, tmp_path) is None


@pytest.mark.parametrize("name", ["ilita", "Projeto-2", "a.b_c", "x" * 80])
def test_a_plain_name_is_accepted(name):
    assert validate_project_name(name, []) == []


@pytest.mark.parametrize(
    "name",
    ["", "   ", "a/b", "..", ".x", "a b", "çedilha", "plots", "PLOTS", "tmp", "run.save", "trash"],
)
def test_a_bad_name_is_refused_with_a_reason(name):
    problems = validate_project_name(name, [], ["tmp", "*.save"])
    assert len(problems) == 1
    assert problems[0]


@pytest.mark.parametrize("name", ["trash", "Trash", "TRASH", " trash "])
def test_trash_is_reserved_for_the_cluster(name):
    """Spec 84 R3.2: ``<remote_root>/trash`` is the cluster's trash."""
    assert validate_project_name(name, []) == ["Este nome é reservado: é a lixeira do cluster"]


def test_renaming_an_item_of_the_root_to_trash_is_refused(tmp_path):
    reason = "Este nome é reservado: é a lixeira do cluster"
    assert root_name_error(tmp_path / "ilita", "Trash", tmp_path) == reason
    assert root_name_error(tmp_path / "a.txt", "trash", tmp_path) == reason
    assert root_name_error(tmp_path / "ilita" / "PDOS", "trash", tmp_path) is None  # below it
    assert root_name_error(tmp_path / "ilita", "trash2", tmp_path) is None


def test_the_root_is_compared_whatever_way_it_is_written(tmp_path):
    """The config may name the root with ``/.``, a ``..`` or a link, the tree with the real path."""
    reason = "Este nome é reservado: é a lixeira do cluster"
    real = tmp_path / "real"
    (real / "ilita" / "PDOS").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    for root in (Path(f"{real}/."), real / "ilita" / "..", link):
        assert root_name_error(real / "ilita", "trash", root) == reason, root
        assert root_name_error(real / "ilita" / "PDOS", "trash", root) is None, root
    # An item of the root that is a link elsewhere is still an item of the root.
    (real / "fora").symlink_to(real / "ilita" / "PDOS", target_is_directory=True)
    assert root_name_error(real / "fora", "trash", real) == reason


def test_a_name_that_exists_is_refused_whatever_its_case():
    assert validate_project_name("Ilita", ["ilita", "outro"])
    assert validate_project_name("ilita", ["ilita"])
    assert validate_project_name("novo", ["ilita"]) == []


def test_create_makes_only_the_folder(tmp_path):
    made = create_project(tmp_path, "ilita")
    assert made == tmp_path / "ilita"
    assert made.is_dir()
    assert list(made.iterdir()) == []
    assert [p.name for p in tmp_path.iterdir()] == ["ilita"]


def test_create_never_reuses_a_folder(tmp_path):
    (tmp_path / "ilita").mkdir()
    (tmp_path / "ilita" / "keep.txt").write_text("mine")
    with pytest.raises(ProjectError, match="Já existe uma pasta com esse nome"):
        create_project(tmp_path, "ilita")
    assert (tmp_path / "ilita" / "keep.txt").read_text() == "mine"
    assert [p.name for p in tmp_path.iterdir()] == ["ilita"]  # no ilita_1


@pytest.mark.parametrize("name", ["../fora", "a/b", "..", "", ".oculta", "plots"])
def test_create_refuses_a_name_that_leaves_the_root_or_is_not_a_project(tmp_path, name):
    root = make(tmp_path, "root")
    with pytest.raises(ProjectError):
        create_project(root / "", name)
    assert not (tmp_path / "fora").exists()
    assert list((tmp_path / "root").iterdir()) == []


def test_create_reports_an_unwritable_root(tmp_path):
    with pytest.raises(ProjectError):
        create_project(tmp_path / "missing", "ilita")
