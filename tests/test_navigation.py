"""Spec 16 R1/R2/R4 without Qt: the history stacks, the breadcrumb arithmetic and the store."""

import json
from pathlib import Path

import pytest

from qe_studio.core.nav_store import RECENT_LIMIT, NavigationStore
from qe_studio.core.navigation import (
    HISTORY_LIMIT,
    NavigationHistory,
    Segment,
    breadcrumb_segments,
    collapse_count,
)

ROOT = Path("/proj")


def everything_exists(_path: Path) -> bool:
    return True


def history_of(*folders: str, limit: int = HISTORY_LIMIT) -> NavigationHistory:
    history = NavigationHistory(limit)
    for folder in folders:
        history.visit(ROOT / folder)
    return history


# -- history -------------------------------------------------------------------------------------
def test_back_and_forward_walk_the_visits():
    history = history_of("a", "b")
    history.visit(ROOT)
    assert history.current == ROOT and history.can_back and not history.can_forward
    assert history.back(everything_exists) == (ROOT / "b", [])
    assert history.back(everything_exists) == (ROOT / "a", [])
    assert history.forward(everything_exists) == (ROOT / "b", [])
    assert history.current == ROOT / "b" and history.can_back and history.can_forward


def test_the_root_a_b_scenario_of_the_spec():
    history = NavigationHistory()
    for folder in (ROOT, ROOT / "a", ROOT / "a" / "b"):
        history.visit(folder)
    assert history.back(everything_exists)[0] == ROOT / "a"
    assert history.back(everything_exists)[0] == ROOT
    assert not history.can_back
    assert history.forward(everything_exists)[0] == ROOT / "a"
    history.visit(ROOT / "c")  # a new folder: "forward" is gone
    assert not history.can_forward and history.current == ROOT / "c"
    assert history.back_stack == [ROOT, ROOT / "a"]


def test_the_same_folder_is_not_pushed_twice_in_a_row():
    history = history_of("a", "a", "b", "b", "a")
    assert history.back_stack == [ROOT / "a", ROOT / "b"] and history.current == ROOT / "a"


def test_nothing_to_go_back_to():
    history = history_of("a")
    assert history.back(everything_exists) == (None, [])
    assert history.forward(everything_exists) == (None, [])
    assert history.current == ROOT / "a"


def test_back_stack_keeps_the_last_fifty():
    history = history_of(*[f"d{n}" for n in range(80)])
    assert len(history.back_stack) == 50
    assert history.back_stack[0] == ROOT / "d29" and history.back_stack[-1] == ROOT / "d78"
    assert history.current == ROOT / "d79"


def test_vanished_folders_are_skipped_and_forgotten():
    history = history_of("a", "gone", "b", "gone", "c")
    existing = lambda path: path.name != "gone"  # noqa: E731
    target, skipped = history.back(existing)  # c ← gone, b
    assert (target, skipped) == (ROOT / "b", [ROOT / "gone"])
    target, skipped = history.back(existing)  # the other "gone" was forgotten with the first
    assert (target, skipped) == (ROOT / "a", [])
    assert history.back_stack == [] and not history.can_back
    # Going forward again no longer meets them.
    assert history.forward(existing) == (ROOT / "b", [])
    assert history.forward(existing) == (ROOT / "c", [])


def test_back_with_only_vanished_folders_stays_put():
    history = history_of("gone", "b")
    assert history.back(lambda path: False) == (None, [ROOT / "gone"])
    assert history.current == ROOT / "b" and not history.can_back


def test_rename_updates_both_stacks_and_the_current_folder():
    history = history_of("run", "run/orbitals", "other", "run/orbitals")
    history.back(everything_exists)  # forward now holds run/orbitals
    history.rename(ROOT / "run", ROOT / "run2")
    assert history.back_stack == [ROOT / "run2", ROOT / "run2" / "orbitals"]
    assert history.forward_stack == [ROOT / "run2" / "orbitals"]
    assert history.current == ROOT / "other"
    history.rename(ROOT / "other", ROOT / "done")
    assert history.current == ROOT / "done"
    history.visit(ROOT / "done")  # selecting the renamed current folder is not a new visit
    assert history.back_stack[-1] == ROOT / "run2" / "orbitals"


# -- breadcrumb ----------------------------------------------------------------------------------
def test_segments_go_from_the_project_to_the_folder():
    segments = breadcrumb_segments(ROOT, ROOT / "a" / "b" / "c")
    assert segments == [
        Segment("proj", ROOT),
        Segment("a", ROOT / "a"),
        Segment("b", ROOT / "a" / "b"),
        Segment("c", ROOT / "a" / "b" / "c"),
    ]
    assert breadcrumb_segments(ROOT, ROOT) == [Segment("proj", ROOT)]
    outside = Path("/elsewhere/x")
    assert breadcrumb_segments(ROOT, outside) == [Segment("/elsewhere/x", outside)]


def test_collapse_hides_the_middle_nearest_the_root_first():
    widths = [50, 40, 40, 40, 60]  # 5 segments, 4 separators of 10
    assert collapse_count(widths, 1000, separator=10, ellipsis=20) == 0
    assert collapse_count(widths, 230 + 40, separator=10, ellipsis=20) == 0  # 230 + 4 * 10 = 270
    assert (
        collapse_count(widths, 269, separator=10, ellipsis=20) == 1
    )  # 50 … 40 40 60 → 50+20+120+60+40
    assert collapse_count(widths, 220, separator=10, ellipsis=20) == 2
    assert collapse_count(widths, 10, separator=10, ellipsis=20) == 3  # root … current, no more


def test_collapse_needs_no_room_for_two_or_fewer_segments():
    assert collapse_count([50], 1) == 0
    assert collapse_count([50, 60], 1) == 0


# -- favorites and recents (spec 16 R4) ---------------------------------------------------------
@pytest.fixture
def project(tmp_path) -> Path:
    for folder in ("a", "a/deep", "b", "c"):
        (tmp_path / "proj" / folder).mkdir(parents=True)
    return tmp_path / "proj"


def store_for(tmp_path, project) -> NavigationStore:
    return NavigationStore(tmp_path / "data" / "navigation.json", project)


def test_favorites_are_saved_with_relative_paths(tmp_path, project):
    store = store_for(tmp_path, project)
    assert store.favorites() == [] and not store.is_favorite(project / "a")
    assert store.add_favorite(project / "a" / "deep") and store.add_favorite(project / "b")
    assert not store.add_favorite(project / "b")  # already one
    assert store.favorites() == [project / "a" / "deep", project / "b"]
    data = json.loads((tmp_path / "data" / "navigation.json").read_text())
    entry = data["projects"][str(project.resolve())]
    assert data["version"] == 1 and entry["favorites"] == ["a/deep", "b"]
    assert str(tmp_path) not in json.dumps(entry)  # nothing absolute
    # A new session reads them back; a copy of the project under another path would too.
    again = store_for(tmp_path, project)
    assert again.favorites() == [project / "a" / "deep", project / "b"]
    assert again.remove_favorite(project / "b") and not again.remove_favorite(project / "b")
    assert store_for(tmp_path, project).favorites() == [project / "a" / "deep"]


def test_projects_do_not_share_their_lists(tmp_path, project):
    other = tmp_path / "other"
    other.mkdir()
    store = store_for(tmp_path, project)
    store.add_favorite(project / "a")
    store.set_root(other)
    assert store.favorites() == []
    store.add_favorite(other)
    store.set_root(project)
    assert store.favorites() == [project / "a"]


def test_folders_outside_the_project_are_ignored(tmp_path, project):
    store = store_for(tmp_path, project)
    assert not store.add_favorite(tmp_path) and not store.touch_recent(tmp_path / "elsewhere")
    assert store.favorites() == [] and store.recents() == []


def test_recents_are_the_last_ten_distinct_folders_newest_first(tmp_path, project):
    store = store_for(tmp_path, project)
    assert not store.touch_recent(project)  # the root is always there anyway
    for n in range(RECENT_LIMIT + 3):
        (project / f"d{n}").mkdir()
        store.touch_recent(project / f"d{n}")
    store.touch_recent(project / "d5")  # again: moves to the front, no duplicate
    recents = store.recents()
    assert len(recents) == RECENT_LIMIT and recents[0] == project / "d5"
    assert recents.count(project / "d5") == 1 and project / "d0" not in recents
    assert not store.touch_recent(project / "d5")  # already first
    store.flush()
    assert store_for(tmp_path, project).recents() == recents


def test_recents_are_written_on_flush_only(tmp_path, project):
    store = store_for(tmp_path, project)
    store.touch_recent(project / "a")
    assert not (tmp_path / "data" / "navigation.json").exists()
    store.flush()
    assert (tmp_path / "data" / "navigation.json").exists()


def test_missing_recents_leave_but_missing_favorites_stay(tmp_path, project):
    store = store_for(tmp_path, project)
    store.add_favorite(project / "a")
    store.touch_recent(project / "b")
    store.touch_recent(project / "c")
    (project / "b").rmdir()
    (project / "a" / "deep").rmdir()
    (project / "a").rmdir()
    assert store.prune_missing_recents() and store.recents() == [project / "c"]
    assert store.favorites() == [project / "a"]  # only the user removes a favorite


def test_rename_moves_favorites_and_recents(tmp_path, project):
    store = store_for(tmp_path, project)
    for folder in ("a", "a/deep", "b"):
        store.add_favorite(project / folder)
        store.touch_recent(project / folder)
    assert store.rename(project / "a", project / "z")
    assert store.favorites() == [project / "z", project / "z" / "deep", project / "b"]
    assert store.recents() == [project / "b", project / "z" / "deep", project / "z"]
    assert not store.rename(project / "nothing", project / "x")
    assert store_for(tmp_path, project).favorites() == store.favorites()  # saved at once
    assert store.rename(project / "z", tmp_path / "gone")  # moved out of the project
    assert store.favorites() == [project / "b"]


def test_a_corrupt_file_is_set_aside_not_overwritten(tmp_path, project):
    path = tmp_path / "data" / "navigation.json"
    path.parent.mkdir()
    path.write_text("{not json")
    store = store_for(tmp_path, project)
    assert "estava corrompido" in (store.load_warning() or "")
    assert store.favorites() == []
    store.add_favorite(project / "a")
    saved = list(path.parent.glob("navigation.json.corrompido-*"))
    assert len(saved) == 1 and saved[0].read_text() == "{not json"
    assert store_for(tmp_path, project).favorites() == [project / "a"]


def test_an_unknown_format_version_is_set_aside_too(tmp_path, project):
    path = tmp_path / "data" / "navigation.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"version": 99, "projects": {}}))
    store = store_for(tmp_path, project)
    assert store.load_warning() is not None  # the file is not ours to read, nor to overwrite
    assert list(path.parent.glob("navigation.json.corrompido-*"))


def test_garbage_inside_an_entry_is_ignored(tmp_path, project):
    path = tmp_path / "data" / "navigation.json"
    path.parent.mkdir()
    entry = {"favorites": ["a", 3, None], "recents": "oops"}
    path.write_text(json.dumps({"version": 1, "projects": {str(project.resolve()): entry}}))
    store = store_for(tmp_path, project)
    assert store.favorites() == [project / "a"] and store.recents() == []
