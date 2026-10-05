"""Compound keys and the store of atom selections (spec 21 R2)."""

import json

import pytest

from qe_studio.core import compounds as compounds_mod
from qe_studio.core.appdirs import data_dir
from qe_studio.core.compounds import (
    CompoundStore,
    GeometryDrift,
    atoms_summary,
    compound_key,
    compound_of,
    geometry_drift,
    normalize_selection,
)
from qe_studio.core.qe.structure import Site


def sites_of(*species, shift=0.0):
    return [Site(i, name, shift + i, shift, 0.0) for i, name in enumerate(species, start=1)]


def test_the_key_is_the_species_sequence():
    assert compound_key(["Al", "Al", "O", "O", "O"]).startswith("Al2O3:")
    assert compound_key(["Al", "O", "Al"]).startswith("AlOAl:")
    assert compound_key(["Al", "Al", "O"]) != compound_key(["Al", "O", "Al"])  # same formula
    assert compound_key(["Al", "O"]) == compound_key(["Al", "O"])
    assert compound_key(["Al"]) != compound_key(["Al", "Al"])


def test_positions_do_not_change_the_compound():
    assert compound_of(sites_of("Si", "Si")) == compound_of(sites_of("Si", "Si", shift=3.5)[:2])
    one, other = compound_of(sites_of("Al", "O", "Al")), compound_of(sites_of("Al", "Al", "O"))
    assert one and other and one.formula == other.formula == "Al2O"
    assert one.key != other.key


def test_no_sites_no_compound():
    assert compound_of([]) is None


def test_normalize_selection():
    valid = [1, 2, 3, 4]
    assert normalize_selection([3, 1], valid) == [1, 3]
    assert normalize_selection([1, 2, 3, 4], valid) is None  # every atom is the default
    assert normalize_selection([9, 10], valid) is None  # nothing that exists
    assert normalize_selection([2, 9, 2], valid) == [2]
    assert normalize_selection(None, valid) is None
    assert normalize_selection([], valid) is None


def test_atoms_summary():
    assert atoms_summary(None, 12) == "todos"
    assert atoms_summary([1, 5, 7], 12) == "3 de 12"


# -- the store ----------------------------------------------------------------------------------
@pytest.fixture
def path(tmp_path):
    return tmp_path / "compounds.json"


def test_nothing_saved_means_every_atom(path):
    store = CompoundStore(path)
    assert store.selection("Al2O3:abc") is None
    assert not path.exists()  # reading never creates the file


def test_round_trip_through_a_new_store(path):
    CompoundStore(path).save("Al2O3:abc", "Al2O3", [4, 1, 2])
    assert json.loads(path.read_text()) == {
        "version": 1,
        "compounds": {"Al2O3:abc": {"formula": "Al2O3", "atoms": [1, 2, 4]}},
    }
    assert CompoundStore(path).selection("Al2O3:abc") == [1, 2, 4]
    assert CompoundStore(path).selection("other") is None


def test_saving_every_atom_removes_the_entry(path):
    store = CompoundStore(path)
    store.save("a", "A", [1])
    store.save("b", "B", [2])
    store.save("a", "A", None)
    assert store.selection("a") is None and CompoundStore(path).selection("a") is None
    assert list(json.loads(path.read_text())["compounds"]) == ["b"]
    store.forget("b")
    assert json.loads(path.read_text())["compounds"] == {}
    before = path.read_text()
    store.forget("never saved")  # nothing to write
    assert path.read_text() == before


def test_the_default_path_is_in_the_data_dir():
    assert CompoundStore().path == data_dir() / "compounds.json"


def test_a_corrupt_file_is_set_aside_not_overwritten(path):
    path.write_text("{ not json")
    store = CompoundStore(path)
    assert store.selection("a") is None
    warning = store.pop_warning()
    assert warning and "corrompido" in warning
    assert store.pop_warning() is None  # said once
    (copy,) = path.parent.glob("compounds.json.corrompido-*")
    assert copy.read_text() == "{ not json"
    store.save("a", "A", [1])
    assert CompoundStore(path).selection("a") == [1]


@pytest.mark.parametrize(
    "content", ["[1, 2]", '{"version": 2, "compounds": {}}', '{"version": 1, "compounds": []}']
)
def test_other_formats_are_set_aside_too(path, content):
    path.write_text(content)
    assert CompoundStore(path).selection("a") is None
    assert len(list(path.parent.glob("compounds.json.corrompido-*"))) == 1


def test_a_file_that_cannot_be_set_aside_is_never_written(path, monkeypatch):
    path.write_text("garbage")

    def refuse(_path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(compounds_mod, "set_aside_corrupt", refuse)
    store = CompoundStore(path)
    store.save("a", "A", [1])
    assert path.read_text() == "garbage"
    assert store.selection("a") == [1]  # kept for the session
    assert store.pop_warning()


def test_bad_entries_are_ignored(path):
    entries = {
        "a": {"atoms": [3, "x", True, -1, 0, 3]},
        "b": {"atoms": "all"},
        "c": 7,
        "d": {"atoms": []},
    }
    path.write_text(json.dumps({"version": 1, "compounds": entries}))
    store = CompoundStore(path)
    assert store.selection("a") == [3]
    assert [store.selection(k) for k in "bcd"] == [None, None, None]


# -- the positions a selection was saved with (spec 27-6 R2) ---------------------------------------
def test_save_keeps_the_positions_rounded_and_the_version(path):
    store = CompoundStore(path)
    store.save("a", "AlO", [2], [(0.123, -1.0, 2.005), (1.9999, 0.0, 0.0)])
    entry = json.loads(path.read_text())
    assert entry["version"] == 1
    assert entry["compounds"]["a"] == {
        "formula": "AlO",
        "atoms": [2],
        "sites": [[0.12, -1.0, 2.0], [2.0, 0.0, 0.0]],
    }
    assert CompoundStore(path).stored_sites("a") == [(0.12, -1.0, 2.0), (2.0, 0.0, 0.0)]


def test_save_merges_with_the_entry(path):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "compounds": {"a": {"formula": "AlO", "atoms": [1], "sites": [[0, 0, 0]], "x": 7}},
            }
        )
    )
    store = CompoundStore(path)
    store.save("a", "AlO", [2])  # without positions: the saved ones stay, and so does "x"
    assert json.loads(path.read_text())["compounds"]["a"] == {
        "formula": "AlO",
        "atoms": [2],
        "sites": [[0, 0, 0]],
        "x": 7,
    }
    store.save("a", "AlO", [1, 2], [(1.0, 0.0, 0.0)])
    entry = json.loads(path.read_text())["compounds"]["a"]
    assert entry["atoms"] == [1, 2] and entry["sites"] == [[1.0, 0.0, 0.0]] and entry["x"] == 7


def test_an_old_file_without_positions_reads_and_saves(path):
    path.write_text(json.dumps({"version": 1, "compounds": {"a": {"formula": "A", "atoms": [1]}}}))
    store = CompoundStore(path)
    assert store.selection("a") == [1] and store.stored_sites("a") is None
    assert store.pop_warning() is None and not list(path.parent.glob("*.corrompido-*"))
    store.save("b", "B", [2])
    data = json.loads(path.read_text())
    assert data["version"] == 1 and data["compounds"]["a"] == {"formula": "A", "atoms": [1]}


@pytest.mark.parametrize(
    "sites",
    ["all", [[0, 0]], [[0, 0, "x"]], [[0, 0, True]], [[0, 0, 0], 5], [[0, 0, float("inf")]]],
)
def test_positions_that_do_not_read_are_none(path, sites):
    path.write_text(json.dumps({"version": 1, "compounds": {"a": {"atoms": [1], "sites": sites}}}))
    store = CompoundStore(path)
    assert store.stored_sites("a") is None and store.selection("a") == [1]


def test_geometry_drift():
    here = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
    assert geometry_drift(here, here) is None
    assert geometry_drift(here, [(0.3, 0.0, 0.0), (1.0, 0.3, 0.0), (2.0, 0.0, 0.0)]) is None
    moved = [(0.0, 0.0, 0.6), (1.0, 2.0, 0.0), (2.0, 0.0, 0.0)]
    assert geometry_drift(here, moved) == GeometryDrift(2, pytest.approx(2.0))  # the worst
    assert geometry_drift(here, moved, tol=3.0) is None
    assert geometry_drift(here, here[:2]) == GeometryDrift(None, None, (3, 2))
