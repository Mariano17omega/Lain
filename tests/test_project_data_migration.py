"""The one-time import from the old per-user files (spec 48 R3): each root takes what is its own,
the old file never changes, and the root's own file always wins."""

import json
import os
from pathlib import Path

import pytest

from qe_studio.core.appdirs import data_dir
from qe_studio.core.compounds import CompoundStore
from qe_studio.core.folder_memory import FolderMemory, legacy_folders
from qe_studio.core.grid_store import GridStore, legacy_grids
from qe_studio.core.nav_store import NavigationStore, legacy_navigation
from qe_studio.core.project_data import (
    COMPOUNDS_FILE,
    FOLDERS_FILE,
    GRIDS_FILE,
    NAVIGATION_FILE,
    PROJECT_DATA_DIR,
    StoreFile,
    fallback_folder,
)


@pytest.fixture
def roots(tmp_path):
    a, b = (tmp_path / "a").resolve(), (tmp_path / "b").resolve()
    for folder in ("ilita/Bandas", "outro/Relax"):
        (a / folder).mkdir(parents=True)
    for folder in ("ilita/Bandas", "so_b"):
        (b / folder).mkdir(parents=True)
    return a, b


def old_file(name: str, data) -> Path:
    """An old per-user file, as Lain before spec 48 wrote it."""
    path = data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def test_folders_of_two_roots_each_take_their_own(roots):
    a, b = roots
    old = old_file(
        FOLDERS_FILE,
        {
            "version": 2,
            "folders": {
                "ilita/Bandas": {"labels": ["G"]},
                "so_b": {"labels": ["B"]},
                f"abs:{a / 'outro' / 'Relax'}": {"labels": ["R"]},
                "abs:/nowhere/x": {"labels": ["N"]},
            },
        },
    )
    before = old.read_bytes()
    memory = FolderMemory(root=a)
    assert memory.labels(a / "ilita" / "Bandas") == ["G"]
    assert memory.labels(a / "outro" / "Relax") == ["R"]  # an abs: key inside the root, re-keyed
    assert memory.labels(a / "so_b") is None
    assert not (a / PROJECT_DATA_DIR).exists()  # importing writes nothing
    memory.set_root(b)
    assert memory.labels(b / "ilita" / "Bandas") == ["G"]
    assert memory.labels(b / "so_b") == ["B"]
    assert memory.labels(b / "outro" / "Relax") is None
    assert old.read_bytes() == before
    memory.set_labels(b / "so_b", ["B2"])  # the first write keeps what was imported
    saved = json.loads((b / PROJECT_DATA_DIR / FOLDERS_FILE).read_text())
    assert saved["folders"] == {"ilita/Bandas": {"labels": ["G"]}, "so_b": {"labels": ["B2"]}}
    assert old.read_bytes() == before


def test_a_version_1_file_imports_the_folders_inside_the_root(roots, tmp_path):
    a, _b = roots
    bands = a / "ilita" / "Bandas"
    (bands / "x.gnu").write_text("")
    old_file(
        FOLDERS_FILE,
        {
            str(bands): {"mappings": {"bands": {"gnu": [str(bands / "x.gnu")]}}},
            str(tmp_path / "other"): {"labels": ["O"]},
        },
    )
    memory = FolderMemory(root=a)
    assert memory.mapping(bands, "bands") == {"gnu": [bands / "x.gnu"]}
    memory.set_labels(bands, ["L"])
    saved = json.loads((a / PROJECT_DATA_DIR / FOLDERS_FILE).read_text())
    assert list(saved["folders"]) == ["ilita/Bandas"]
    assert saved["folders"]["ilita/Bandas"]["mappings"] == {"bands": {"gnu": ["x.gnu"]}}


def test_legacy_folders_is_pure_and_takes_an_exists_check(tmp_path):
    root = tmp_path / "r"
    data = {"version": 2, "folders": {"x": {}, "y": {}, f"abs:{root}/z": {}, "abs:/o": {}}}
    kept = legacy_folders(data, root, lambda path: path.name == "x")
    assert kept == {"version": 2, "folders": {"x": {}, f"abs:{root}/z": {}}}
    assert legacy_folders({"version": 9, "folders": {}}, root, bool)["folders"] == {}
    assert legacy_folders([1, 2], root, bool)["folders"] == {}


def test_grids_of_the_root_and_without_cells_are_imported(roots):
    a, _b = roots

    def cell(path):
        return {"row": 0, "col": 0, "path": path, "kind": "bands", "partner": None, "title": ""}

    old = old_file(
        GRIDS_FILE,
        {
            "version": 1,
            "grids": {
                "Daqui": {"rows": 1, "cols": 2, "cells": [cell("gone"), cell("ilita/Bandas")]},
                "Outra": {"rows": 1, "cols": 1, "cells": [cell("so_b")]},
                "Vazia": {"rows": 2, "cols": 2, "cells": []},
                "Absoluta": {"rows": 1, "cols": 1, "cells": [cell(f"abs:{a / 'outro'}")]},
                "Fora": {"rows": 1, "cols": 1, "cells": [cell("abs:/nowhere")]},
            },
        },
    )
    before = old.read_bytes()
    store = GridStore(root=a)
    assert store.names() == ["Absoluta", "Daqui", "Vazia"]
    assert store.get("Daqui").cells[1].ref.path == a / "ilita" / "Bandas"
    assert old.read_bytes() == before
    assert not (a / PROJECT_DATA_DIR).exists()


def test_legacy_grids_drops_another_format(tmp_path):
    assert legacy_grids({"version": 2, "grids": {}}, tmp_path, bool) == {}
    assert legacy_grids({"version": 1, "grids": []}, tmp_path, bool) == {}


def test_compounds_are_imported_whole(roots):
    a, b = roots
    data = {"version": 1, "compounds": {"Al O": {"formula": "AlO", "atoms": [1]}}}
    old_file(COMPOUNDS_FILE, data)
    for root in (a, b):
        store = CompoundStore()
        store.set_root(root)
        assert store.selection("Al O") == [1]


def test_navigation_imports_only_the_current_root_under_a_dot(roots):
    a, b = roots
    old_file(
        NAVIGATION_FILE,
        {
            "version": 1,
            "projects": {
                str(a): {"favorites": ["ilita"], "recents": ["outro/Relax"]},
                str(b): {"favorites": ["so_b"], "recents": []},
            },
        },
    )
    store = NavigationStore(root=a)
    assert store.favorites() == [a / "ilita"] and store.recents() == [a / "outro" / "Relax"]
    store.add_favorite(a / "outro")
    saved = json.loads((a / PROJECT_DATA_DIR / NAVIGATION_FILE).read_text())
    assert saved == {
        "version": 1,
        "projects": {".": {"favorites": ["ilita", "outro"], "recents": ["outro/Relax"]}},
    }
    assert legacy_navigation({"version": 1, "projects": {}}, str(a)) == {}


def test_the_root_file_is_never_replaced_by_the_old_one(roots):
    a, _b = roots
    old = old_file(
        FOLDERS_FILE, {"version": 2, "folders": {"ilita/Bandas": {"labels": ["antigo"]}}}
    )
    own = a / PROJECT_DATA_DIR / FOLDERS_FILE
    own.parent.mkdir()
    own.write_text(json.dumps({"version": 2, "folders": {"outro/Relax": {"labels": ["mine"]}}}))
    memory = FolderMemory(root=a)
    assert memory.labels(a / "ilita" / "Bandas") is None
    assert memory.labels(a / "outro" / "Relax") == ["mine"]
    memory.set_labels(a / "outro", ["L"])
    assert "antigo" not in own.read_text()
    assert json.loads(old.read_text())["folders"] == {"ilita/Bandas": {"labels": ["antigo"]}}


def test_a_corrupt_old_file_is_left_alone(roots):
    a, _b = roots
    data_dir().mkdir(parents=True, exist_ok=True)
    for name in (FOLDERS_FILE, GRIDS_FILE, COMPOUNDS_FILE, NAVIGATION_FILE):
        (data_dir() / name).write_text("{broken", encoding="utf-8")
    memory, navigation, grids = FolderMemory(root=a), NavigationStore(root=a), GridStore(root=a)
    compounds = CompoundStore()
    compounds.set_root(a)
    assert memory.labels(a / "ilita") is None and memory.load_warning() is None
    assert navigation.favorites() == [] and navigation.load_warning() is None
    assert grids.names() == [] and grids.pop_warning() is None
    assert compounds.selection("x") is None and compounds.pop_warning() is None
    assert sorted(p.name for p in data_dir().iterdir()) == sorted(
        [FOLDERS_FILE, GRIDS_FILE, COMPOUNDS_FILE, NAVIGATION_FILE]
    )  # no ".corrompido" copy: the old files are not the stores' to set aside
    assert all((data_dir() / name).read_text() == "{broken" for name in os.listdir(data_dir()))


def test_once_the_root_file_exists_the_old_one_is_not_read(roots, monkeypatch):
    a, _b = roots
    old_file(FOLDERS_FILE, {"version": 2, "folders": {"ilita/Bandas": {"labels": ["G"]}}})
    FolderMemory(root=a).set_labels(a / "outro", ["L"])  # the first write: the import is saved

    def no_read(self):
        raise AssertionError(f"read the old {self.name}")

    monkeypatch.setattr(StoreFile, "read_legacy", no_read)
    memory = FolderMemory(root=a)
    assert memory.labels(a / "ilita" / "Bandas") == ["G"]
    assert memory.labels(a / "outro") == ["L"]


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores modes")
def test_the_fallback_folder_imports_too(roots):
    a, _b = roots
    old_file(FOLDERS_FILE, {"version": 2, "folders": {"ilita/Bandas": {"labels": ["G"]}}})
    a.chmod(0o555)
    try:
        memory = FolderMemory(root=a)
        assert memory.labels(a / "ilita" / "Bandas") == ["G"]
        memory.set_labels(a / "outro", ["L"])
    finally:
        a.chmod(0o755)
    saved = json.loads((fallback_folder(a) / FOLDERS_FILE).read_text())
    assert set(saved["folders"]) == {"ilita/Bandas", "outro"}
