"""The folders of the cluster tree (spec 65 R4): what a new listing keeps, drops and forgets."""

import time

import pytest

from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.cluster.remote_model import RemoteTreeModel


@pytest.fixture
def model(qapp):
    tree = RemoteTreeModel(ThemeManager("dark"))
    tree.reset("/r")
    return tree


def names(model: RemoteTreeModel, folder: str) -> list[str]:
    item = model._item_for(folder)
    return [item.child(row).text() for row in range(item.rowCount())] if item else []


def test_a_folder_that_goes_takes_what_was_listed_below_it_and_only_that(model):
    model.set_subfolders("/r", ["a", "ab", "b"])
    model.set_subfolders("/r/a", ["x"])
    model.set_subfolders("/r/a/x", ["deep"])
    model.set_subfolders("/r/ab", ["y"])
    model.set_subfolders("/r", ["ab", "b"])  # "a" is gone: "ab" only shares its first letter
    assert names(model, "/r") == ["ab", "b"]
    assert set(model._items) == {"/r/ab", "/r/b", "/r/ab/y"}
    assert "/r/a" not in model._listed and "/r/a/x" not in model._listed
    assert "/r/ab" in model._listed  # what was listed below the kept ones is kept
    assert names(model, "/r/ab") == ["y"]


def test_another_order_starts_over_and_forgets_what_was_below(model):
    model.set_subfolders("/r", ["a", "b"])
    model.set_subfolders("/r/a", ["x"])
    model.set_subfolders("/r", ["b", "a"])
    assert names(model, "/r") == ["b", "a"]
    assert set(model._items) == {"/r/a", "/r/b"} and "/r/a" not in model._listed


def test_a_folder_asked_for_or_failed_is_forgotten_with_its_parent(model):
    model.set_subfolders("/r", ["a"])
    model.request("/r/a")
    model.mark_failed("/r/a")
    model.set_subfolders("/r", [])
    assert not model._requested and not model._failed and not model._items


def test_a_listing_of_thousands_of_subfolders_is_fast(model):
    many = [f"d{i:05d}" for i in range(5000)]
    model.set_subfolders("/r", many)
    for name in many[:200]:
        model.set_subfolders(f"/r/{name}", ["sub"])
    started = time.perf_counter()
    model.set_subfolders("/r", many[2000:])  # the first 2000, with the listed ones, go
    model.set_subfolders("/r", many[::-1])  # another order: all start over
    assert time.perf_counter() - started < 3.0
    assert names(model, "/r")[:2] == ["d04999", "d04998"] and len(model._items) == 5000
