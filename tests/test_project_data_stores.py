"""The four stores follow the root (spec 48 R2, R4): their files live in ``<root>/.lain/``, each root
has its own, a copy of the root takes them along, and a read-only root falls back to the data dir."""

import json
import os
import shutil
from pathlib import Path

import pytest

from qe_studio.core.appdirs import data_dir
from qe_studio.core.compounds import CompoundStore
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.grid_store import GridStore
from qe_studio.core.nav_store import ROOT_KEY, NavigationStore
from qe_studio.core.plotting.grid import GridCell, GridSpec, PlotRef
from qe_studio.core.project_data import (
    COMPOUNDS_FILE,
    FOLDERS_FILE,
    GRIDS_FILE,
    NAVIGATION_FILE,
    PROJECT_DATA_DIR,
    fallback_folder,
)

FILES = (FOLDERS_FILE, GRIDS_FILE, COMPOUNDS_FILE, NAVIGATION_FILE)

as_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions"
)


def make_root(path: Path) -> Path:
    for folder in ("ilita/Bandas", "ilita/PDOS", "outro/Relax"):
        (path / folder).mkdir(parents=True)
    (path / "ilita" / "Bandas" / "bands.gnu").write_text("")
    return path


@pytest.fixture
def root_a(tmp_path):
    return make_root(tmp_path / "a")


@pytest.fixture
def root_b(tmp_path):
    return make_root(tmp_path / "b")


def stores(root: Path):
    """Fresh stores without a path, as the window builds them, set on ``root``."""
    memory, navigation = FolderMemory(), NavigationStore()
    grids, compounds = GridStore(), CompoundStore()
    for store in (memory, navigation, grids, compounds):
        store.set_root(root)
    return memory, navigation, grids, compounds


def grid(root: Path) -> GridSpec:
    ref = PlotRef(root / "ilita" / "Bandas", "bands")
    return GridSpec("Al", 1, 2, [GridCell(0, 0, ref, "bandas")])


def fill(root: Path) -> None:
    """One entry in each store of ``root``."""
    memory, navigation, grids, compounds = stores(root)
    bands = root / "ilita" / "Bandas"
    memory.set_mapping(bands, "bands", {"gnu": [bands / "bands.gnu"]})
    memory.set_labels(bands, ["G", "X"])
    navigation.add_favorite(bands)
    navigation.touch_recent(root / "ilita" / "PDOS")
    navigation.flush()
    grids.save(grid(root))
    compounds.save("Al Al O", "Al2O", [1, 3])


def test_each_store_writes_in_the_root_settings_folder_and_reads_back(root_a):
    fill(root_a)
    assert sorted(p.name for p in (root_a / PROJECT_DATA_DIR).iterdir()) == sorted(FILES)
    memory, navigation, grids, compounds = stores(root_a)
    bands = root_a / "ilita" / "Bandas"
    assert memory.path == root_a / PROJECT_DATA_DIR / FOLDERS_FILE
    assert memory.labels(bands) == ["G", "X"]
    assert navigation.favorites() == [bands]
    assert navigation.recents() == [root_a / "ilita" / "PDOS"]
    assert grids.get("Al") == grid(root_a)
    assert compounds.selection("Al Al O") == [1, 3]
    assert not any(data_dir().glob("*.json"))  # nothing in the old per-user place


def test_the_folder_is_made_by_the_first_write_only(root_a):
    memory, navigation, grids, compounds = stores(root_a)
    memory.labels(root_a), navigation.favorites(), grids.names(), compounds.selection("x")
    assert memory.load_warning() is None
    assert not (root_a / PROJECT_DATA_DIR).exists()


def test_two_roots_in_one_session_keep_their_own_entries(root_a, root_b):
    memory, navigation, grids, compounds = (
        FolderMemory(),
        NavigationStore(),
        GridStore(),
        CompoundStore(),
    )
    for root, name, favorite in ((root_a, "A", "ilita"), (root_b, "B", "outro")):
        for store in (memory, navigation, grids, compounds):
            store.set_root(root)
        memory.set_labels(root / "ilita" / "Bandas", [name])
        navigation.add_favorite(root / favorite)
        grids.save(GridSpec(f"grade {name}", 1, 1, []))
        compounds.save(f"key {name}", "X", [1])
    for store in (memory, navigation, grids, compounds):
        store.set_root(root_a)
    assert memory.labels(root_a / "ilita" / "Bandas") == ["A"]
    assert navigation.favorites() == [root_a / "ilita"]
    assert grids.names() == ["grade A"]
    assert compounds.selection("key A") == [1] and compounds.selection("key B") is None
    alone = FolderMemory(root=root_b)
    assert alone.labels(root_b / "ilita" / "Bandas") == ["B"]
    assert GridStore(root=root_b).names() == ["grade B"]


def test_a_mapping_of_one_root_is_not_seen_in_another(root_a, root_b):
    memory = FolderMemory(root=root_a)
    memory.set_labels(root_a / "outro" / "Relax", ["L"])
    memory.set_root(root_b)
    assert memory.labels(root_b / "outro" / "Relax") is None
    assert not (root_b / PROJECT_DATA_DIR).exists()


def test_a_copy_of_the_root_takes_its_settings_along(root_a, tmp_path):
    fill(root_a)
    copy = tmp_path / "elsewhere" / "copia"
    shutil.copytree(root_a, copy)
    memory, navigation, grids, compounds = stores(copy)
    bands = copy / "ilita" / "Bandas"
    assert memory.mapping(bands, "bands") == {"gnu": [bands / "bands.gnu"]}
    assert memory.labels(bands) == ["G", "X"]
    assert navigation.favorites() == [bands]
    assert navigation.recents() == [copy / "ilita" / "PDOS"]
    assert grids.get("Al") == grid(copy)
    assert compounds.selection("Al Al O") == [1, 3]


def test_navigation_keys_the_root_entry_by_a_dot(root_a):
    fill(root_a)
    data = json.loads((root_a / PROJECT_DATA_DIR / NAVIGATION_FILE).read_text())
    assert list(data["projects"]) == [ROOT_KEY] == ["."]


def test_a_store_with_a_path_never_makes_the_folder(root_a, tmp_path):
    memory = FolderMemory(tmp_path / "m.json", root=root_a)
    navigation = NavigationStore(tmp_path / "n.json", root=root_a)
    grids, compounds = GridStore(tmp_path / "g.json", root_a), CompoundStore(tmp_path / "c.json")
    compounds.set_root(root_a)
    memory.set_labels(root_a / "ilita", ["L"])
    navigation.add_favorite(root_a / "ilita")
    grids.save(grid(root_a))
    compounds.save("k", "X", [1])
    assert not (root_a / PROJECT_DATA_DIR).exists()
    assert {p.name for p in tmp_path.glob("*.json")} == {"m.json", "n.json", "g.json", "c.json"}
    assert NavigationStore(tmp_path / "n.json", root=root_a).favorites() == [root_a / "ilita"]


def test_changing_root_writes_pending_recents_to_the_old_file(root_a, root_b):
    navigation = NavigationStore(root=root_a)
    navigation.touch_recent(root_a / "ilita")  # pending: written by the next flush
    navigation.set_root(root_b)
    assert navigation.recents() == []
    assert NavigationStore(root=root_a).recents() == [root_a / "ilita"]
    assert not (root_b / PROJECT_DATA_DIR).exists()


# -- read-only root (R4) -----------------------------------------------------------------------
@as_root
def test_a_read_only_root_keeps_the_settings_in_the_data_dir(root_a):
    root_a.chmod(0o555)
    try:
        fill(root_a)
        memory = FolderMemory(root=root_a)
        warning = memory.load_warning()
        assert memory.labels(root_a / "ilita" / "Bandas") == ["G", "X"]
    finally:
        root_a.chmod(0o755)
    fallback = fallback_folder(root_a)
    assert not (root_a / PROJECT_DATA_DIR).exists()
    assert sorted(p.name for p in fallback.iterdir()) == sorted(FILES)
    assert warning is not None and "não é gravável" in warning and str(fallback) in warning


@as_root
def test_back_to_the_root_folder_when_it_is_writable_again(root_a):
    root_a.chmod(0o555)
    try:
        memory = FolderMemory(root=root_a)
        memory.set_labels(root_a / "ilita", ["fallback"])
        assert memory.path.parent == fallback_folder(root_a)
    finally:
        root_a.chmod(0o755)
    memory.set_root(root_a)
    assert memory.path == root_a / PROJECT_DATA_DIR / FOLDERS_FILE
    assert memory.load_warning() is None
    assert memory.labels(root_a / "ilita") is None  # what went to the fallback stays there
    assert (fallback_folder(root_a) / FOLDERS_FILE).is_file()
