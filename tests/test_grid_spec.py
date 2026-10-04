"""Spec 23 R1: the definition of a grid of plots and the store of saved grids."""

import json
import shutil

import pytest

from qe_studio.core import grid_store as grid_store_mod
from qe_studio.core.appdirs import data_dir
from qe_studio.core.grid_store import GridStore
from qe_studio.core.plotting.grid import MAX_SIZE, GridCell, GridSpec, PlotRef


def ref(path, kind="bands", partner=None):
    return PlotRef(path, kind, partner)


def spec_of(*cells, rows=1, cols=2, name="g"):
    return GridSpec(name, rows, cols, list(cells))


# -- validate -------------------------------------------------------------------------------------
def test_a_valid_grid_has_no_errors(tmp_path):
    grid = spec_of(GridCell(0, 0, ref(tmp_path / "a")), GridCell(0, 1, ref(tmp_path / "b"), "B"))
    assert grid.validate() == []


@pytest.mark.parametrize(
    "grid, expected",
    [
        (GridSpec("", 1, 1, [GridCell(0, 0, PlotRef(".", "bands"))]), "Dê um nome à grade."),
        (GridSpec("a/b", 1, 1, [GridCell(0, 0, PlotRef(".", "bands"))]), "não pode conter"),
        (GridSpec("g", MAX_SIZE + 1, 1, [GridCell(0, 0, PlotRef(".", "bands"))]), "de 1 a 6"),
        (GridSpec("g", 0, 1, [GridCell(0, 0, PlotRef(".", "bands"))]), "de 1 a 6"),
        (GridSpec("g", 1, 1, []), "Adicione ao menos uma célula."),
        (GridSpec("g", 1, 1, [GridCell(0, 0, None)]), "Célula 1: escolha um gráfico."),
        (
            GridSpec("g", 1, 2, [GridCell(0, 2, PlotRef(".", "bands"))]),
            "Célula 1: posição (1, 3) fora da grade 1 × 2.",
        ),
        (
            GridSpec(
                "g", 1, 2, [GridCell(0, 1, PlotRef(".", "a")), GridCell(0, 1, PlotRef(".", "b"))]
            ),
            "Células 1 e 2 estão na mesma posição (1, 2).",
        ),
    ],
)
def test_each_problem_has_its_message(grid, expected):
    errors = grid.validate()
    assert len(errors) == 1 and expected in errors[0], errors


def test_seven_by_one_is_too_big():
    grid = GridSpec("g", 7, 1, [GridCell(0, 0, PlotRef(".", "bands"))])
    assert grid.validate() == ["Linhas e colunas vão de 1 a 6."]


# -- the store ------------------------------------------------------------------------------------
@pytest.fixture
def path(tmp_path):
    return tmp_path / "data" / "grids.json"


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "project"
    for name in ("bands", "pdos", "scf"):
        (folder / name).mkdir(parents=True)
    (folder / "scf" / "scf.out").write_text("")
    return folder


def full_spec(root, outside):
    return GridSpec(
        "Al",
        2,
        2,
        [
            GridCell(0, 0, ref(root / "bands"), "Bandas"),
            GridCell(0, 1, ref(root / "bands", "bands_dos", root / "pdos")),
            GridCell(1, 0, ref(root / "scf" / "scf.out", "scf")),
            GridCell(1, 1, ref(outside, "relax")),
        ],
    )


def test_the_default_file_is_in_the_data_dir():
    assert GridStore().path == data_dir() / "grids.json"


def test_round_trip_with_paths_relative_to_the_root(path, root, tmp_path):
    spec = full_spec(root, tmp_path / "elsewhere")
    store = GridStore(path, root)
    store.save(spec)
    assert store.names() == ["Al"]
    assert GridStore(path, root).get("Al") == spec
    cells = json.loads(path.read_text())["grids"]["Al"]["cells"]
    assert [c["path"] for c in cells] == [
        "bands",
        "bands",
        "scf/scf.out",
        f"abs:{tmp_path / 'elsewhere'}",
    ]
    assert cells[1]["partner"] == "pdos" and cells[0]["partner"] is None


def test_a_moved_project_keeps_its_grids(path, root, tmp_path):
    GridStore(path, root).save(full_spec(root, tmp_path / "elsewhere"))
    moved = tmp_path / "moved"
    shutil.move(root, moved)
    spec = GridStore(path, moved).get("Al")
    assert spec is not None
    assert spec.cells[0].ref == ref(moved / "bands")
    assert spec.cells[1].ref == ref(moved / "bands", "bands_dos", moved / "pdos")
    assert spec.cells[3].ref == ref(tmp_path / "elsewhere", "relax")  # outside: as it was


def test_another_project_resolves_them_there_and_deletes_nothing(path, root, tmp_path):
    GridStore(path, root).save(full_spec(root, tmp_path / "elsewhere"))
    other = tmp_path / "other"
    other.mkdir()
    store = GridStore(path, other)
    spec = store.get("Al")
    assert spec is not None and spec.cells[0].ref.path == other / "bands"
    assert not spec.cells[0].ref.path.exists()  # unavailable there, still saved
    assert GridStore(path, root).get("Al") == full_spec(root, tmp_path / "elsewhere")


def test_save_keeps_the_settings_and_delete_removes_the_grid(path, root, tmp_path):
    store = GridStore(path, root)
    spec = full_spec(root, tmp_path / "x")
    store.save_params("Al", {"cell_width": 4.0})  # not saved yet: nothing
    assert store.params("Al") == {}
    store.save(spec)
    store.save_params("Al", {"cell_width": 4.0})
    spec.rows = 3
    store.save(spec)
    assert GridStore(path, root).params("Al") == {"cell_width": 4.0}
    store.delete("Al")
    assert GridStore(path, root).names() == [] and store.get("Al") is None


def test_rename_follows_the_folders(path, root, tmp_path):
    store = GridStore(path, root)
    store.save(full_spec(root, tmp_path / "x"))
    (root / "pdos").rename(root / "dos")
    store.rename(root / "pdos", root / "dos")
    spec = GridStore(path, root).get("Al")
    assert spec is not None and spec.cells[1].ref.partner == root / "dos"
    assert spec.cells[0].ref.path == root / "bands"  # untouched
    store.rename(root / "scf", root / "scf2")
    assert GridStore(path, root).get("Al").cells[2].ref.path == root / "scf2" / "scf.out"


def test_a_corrupt_file_is_set_aside_and_never_overwritten(path, root):
    path.parent.mkdir(parents=True)
    path.write_text("{ not json")
    store = GridStore(path, root)
    assert store.names() == []
    warning = store.pop_warning()
    assert warning and "corrompido" in warning and store.pop_warning() is None
    (copy,) = path.parent.glob("grids.json.corrompido-*")
    assert copy.read_text() == "{ not json"


@pytest.mark.parametrize("content", ['{"version": 9, "grids": {}}', "[1, 2]", '{"grids": 3}'])
def test_other_formats_are_set_aside_too(path, content):
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert GridStore(path).names() == []
    assert len(list(path.parent.glob("grids.json.corrompido-*"))) == 1


def test_a_file_that_cannot_be_set_aside_is_never_written(path, root, monkeypatch):
    path.parent.mkdir(parents=True)
    path.write_text("garbage")

    def refuse(_path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(grid_store_mod, "set_aside_corrupt", refuse)
    store = GridStore(path, root)
    store.save(GridSpec("g", 1, 1, [GridCell(0, 0, ref(root / "bands"))]))
    assert path.read_text() == "garbage"
    assert store.names() == ["g"]  # kept for the session
    assert store.pop_warning()


def test_an_unreadable_entry_is_skipped(path, root):
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "grids": {"bad": {"rows": 1}, "worse": 3}}))
    store = GridStore(path, root)
    assert store.get("bad") is None and store.get("worse") is None
