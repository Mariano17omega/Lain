"""Spec 16 R3: the quick filter of the grid and the tree, by name, badge, state and visual type."""

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from grid_helpers import names, reset_modifiers, rows, show_folder, tree_names
from qe_studio.core.filtering import CategoryFilter

from viewer_helpers import CTRL, key, open_text


def set_name(bar, text: str) -> None:
    bar.open()
    bar.field.setText(text)
    bar.flush()  # the typing delay is for people


def tick(bar, group: str, value: str, on: bool = True) -> None:
    bar._actions[(group, value)].setChecked(on)


@pytest.fixture
def bands(qtbot, main_window, demo_project) -> Path:
    folder = demo_project / "03_bands"
    show_folder(qtbot, main_window, folder)
    return folder


# -- grid: name ----------------------------------------------------------------------------------
def test_grid_filters_by_name_and_counts(qtbot, main_window, bands):
    files = main_window.files
    everything = names(files)
    assert files.header.count.text() == f"({len(everything) - 1})" and files.filter_bar.isHidden()
    set_name(files.filter_bar, "SCF")  # a substring, any case
    assert names(files) == ["..", "scf.out"]  # ".." is never filtered
    assert files.header.count.text() == f"(1 de {len(everything) - 1})"
    qtbot.keyClick(files.filter_bar.field, Qt.Key.Key_Escape)
    assert names(files) == everything and files.filter_bar.isHidden()
    assert files.header.count.text() == f"({len(everything) - 1})"
    assert files.view.hasFocus()


def test_wildcards_in_the_name_filter(main_window, bands):
    files = main_window.files
    set_name(files.filter_bar, "ba*.out")
    assert names(files) == ["..", "bands.out", "bands_pp.out"]
    set_name(files.filter_bar, "bands.?ut")
    assert names(files) == ["..", "bands.out"]
    set_name(files.filter_bar, "[")  # no pattern language besides * and ?
    assert names(files) == [".."]


def test_a_filter_stays_with_the_folder_it_was_typed_in(qtbot, main_window, bands, demo_project):
    files = main_window.files
    set_name(files.filter_bar, "scf")
    show_folder(qtbot, main_window, demo_project / "04_pdos")
    assert files.filter_bar.isHidden() and not files.proxy.filtering
    assert "nscf.out" in names(files) and "projwfc.out" in names(files)


def test_the_grid_folder_survives_a_name_that_matches_nothing(main_window, bands):
    files = main_window.files
    set_name(files.filter_bar, "zzz")
    assert names(files) == [".."]
    assert files.folder == bands and files.view.rootIndex().isValid()


# -- Ctrl+F follows the focus --------------------------------------------------------------------
def test_ctrl_f_opens_the_filter_of_the_panel_with_the_focus(qtbot, main_window, bands):
    window = main_window
    window.files.view.setFocus()
    key(qtbot, window.files.view, "F", CTRL)
    reset_modifiers(qtbot, window.files.view.viewport())
    assert not window.files.filter_bar.isHidden() and window.files.filter_bar.field.hasFocus()
    assert window.explorer.filter_bar.isHidden()
    window.files.filter_bar.dismiss()
    window.explorer.tree.setFocus()
    key(qtbot, window.explorer.tree, "F", CTRL)
    reset_modifiers(qtbot, window.explorer.tree.viewport())
    assert not window.explorer.filter_bar.isHidden() and window.files.filter_bar.isHidden()


def test_ctrl_f_in_the_text_viewer_is_the_search_not_the_filter(qtbot, main_window, bands):
    window = main_window
    viewer = open_text(qtbot, window, bands / "bands.in")
    viewer.editor.setFocus()
    key(qtbot, viewer.editor, "F", CTRL)
    reset_modifiers(qtbot, viewer.editor.viewport())
    assert not viewer.search.isHidden()
    assert window.files.filter_bar.isHidden() and window.explorer.filter_bar.isHidden()
    viewer.search.dismiss()  # and the other way round
    window.files.view.setFocus()
    key(qtbot, window.files.view, "F", CTRL)
    reset_modifiers(qtbot, window.files.view.viewport())
    assert viewer.search.isHidden() and not window.files.filter_bar.isHidden()


# -- grid: state and visual type -----------------------------------------------------------------
def test_state_filter_lists_only_the_truncated_output(qtbot, main_window, demo_project):
    window, files = main_window, main_window.files
    folder = demo_project / "03_bands"
    text = (folder / "scf.out").read_text()
    (folder / "cut.out").write_text(text[: len(text) // 2])  # no "JOB DONE"
    show_folder(qtbot, window, folder)
    window.service.detect_now(folder)  # fills the sniff cache the states come from
    bar = files.filter_bar
    bar.open()
    tick(bar, "states", "INCOMPLETO")
    assert names(files) == ["..", "cut.out"]  # folders and the finished outputs are out
    assert bar.chips_layout.count() == 1 and not bar.chips_host.isHidden()
    tick(bar, "states", "OK")
    listed = names(files)  # ticking more values of a group widens it
    assert "cut.out" in listed and "scf.out" in listed and "bands.in" not in listed
    chip = bar.chips_layout.itemAt(0).widget()
    chip.click()  # chips remove their category
    chip = bar.chips_layout.itemAt(0).widget()
    chip.click()
    assert not bar.is_active and "bands.in" in names(files)


def test_visual_type_filter(qtbot, main_window, bands):
    files = main_window.files
    bar = files.filter_bar
    bar.open()
    tick(bar, "visuals", "inputs")
    assert names(files) == ["..", "bands.in"]
    tick(bar, "visuals", "inputs", on=False)
    tick(bar, "visuals", "dados")
    assert names(files) == ["..", "bands.dat.gnu"]
    set_name(bar, "dat")
    assert names(files) == ["..", "bands.dat.gnu"]  # name and category both apply
    set_name(bar, "bands.in")
    assert names(files) == [".."]


# -- badges --------------------------------------------------------------------------------------
def test_badge_filter_lists_the_relax_folder_once_detected(qtbot, main_window, demo_project):
    window, files = main_window, main_window.files
    show_folder(qtbot, window, demo_project, up=False)
    bar = files.filter_bar
    bar.open()
    tick(bar, "badges", "RELAX")
    # Detection of the folders listed was asked for; the filter settles when it arrives.
    qtbot.waitUntil(lambda: names(files) == ["01_relax"], timeout=10_000)
    assert not any(files.proxy.is_pending(i) for i in rows(files))


def test_undetected_folders_wait_as_detectando(main_window, demo_project, monkeypatch):
    window, files = main_window, main_window.files
    requested = []
    monkeypatch.setattr(window.service, "peek_results", lambda folder: None)  # nothing cached
    monkeypatch.setattr(
        window.service, "request", lambda folder, fresh=False: requested.append(folder.name)
    )
    window.explorer.select_path(demo_project / "04_pdos")  # keeps ".." out of the way
    window.on_folder_selected(demo_project)
    bar = files.filter_bar
    bar.open()
    requested.clear()  # painting the tree asked for some already; only the filter's count
    tick(bar, "badges", "RELAX")
    folders = ["01_relax", "02_scf", "03_bands", "04_pdos"]
    assert names(files) == folders  # all still listed
    assert all(
        files.proxy.is_pending(files.proxy.index(r, 0, files.view.rootIndex())) for r in range(4)
    )
    assert sorted(requested) == folders  # and their detection asked for
    monkeypatch.undo()


# -- tree ----------------------------------------------------------------------------------------
def test_tree_filters_the_loaded_folders_and_keeps_ancestors(qtbot, main_window, demo_project):
    window = main_window
    window.explorer.select_path(demo_project / "04_pdos")  # opens it: its files are loaded
    qtbot.waitUntil(
        lambda: (
            "nscf.out"
            in tree_names(window, window.explorer.proxy.index_for(demo_project / "04_pdos"))
        )
    )
    everything = tree_names(window)
    assert everything == ["01_relax", "02_scf", "03_bands", "04_pdos"]
    bar = window.explorer.filter_bar
    set_name(bar, "band")
    assert tree_names(window) == ["03_bands"]
    set_name(bar, "nscf")  # a file in a loaded folder: its folder stays as the ancestor
    assert tree_names(window) == ["04_pdos"]
    assert tree_names(window, window.explorer.proxy.index_for(demo_project / "04_pdos")) == [
        "nscf.out"
    ]
    qtbot.keyClick(bar.field, Qt.Key.Key_Escape)
    assert tree_names(window) == everything and window.explorer.tree.hasFocus()
    assert not window.explorer.proxy.isRecursiveFilteringEnabled()


def test_tree_badge_filter(qtbot, main_window, demo_project):
    window = main_window
    for folder in ("01_relax", "02_scf", "03_bands", "04_pdos"):
        window.service.detect_now(demo_project / folder)
    bar = window.explorer.filter_bar
    bar.open()
    tick(bar, "badges", "BANDS")
    assert tree_names(window) == ["03_bands"]
    tick(bar, "badges", "BANDS", on=False)
    assert tree_names(window) == ["01_relax", "02_scf", "03_bands", "04_pdos"]


def test_navigating_to_a_filtered_out_folder_clears_the_tree_filter(main_window, demo_project):
    window = main_window
    bar = window.explorer.filter_bar
    set_name(bar, "band")
    assert tree_names(window) == ["03_bands"]
    window.navigation.go_to(demo_project / "02_scf")  # e.g. a breadcrumb click
    assert not bar.is_active and window.explorer.current_path() == demo_project / "02_scf"
    assert window.files.folder == demo_project / "02_scf"


def test_filtering_alone_starts_no_detection(main_window, demo_project, monkeypatch):
    """Rows are judged from caches: ``set_filters`` never schedules detection (painting does,
    but that is not the filter)."""
    window = main_window
    asked = []
    monkeypatch.setattr(window.service, "results", lambda folder: asked.append(folder))
    monkeypatch.setattr(window.service, "request", lambda folder, fresh=False: asked.append(folder))
    for proxy in (window.explorer.proxy, window.files.proxy):
        category = CategoryFilter(badges=frozenset({"SCF"}), states=frozenset({"OK"}))
        proxy.set_filters("scf", category)
        proxy.set_filters("", CategoryFilter())
    assert asked == []
