"""Spec 16 R5: several items selected in the grid, the shorter menu and Enter on a selection."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QMenu

from grid_helpers import (
    click,
    index_of,
    menu_texts,
    reset_modifiers,
    rows,
    select_names,
    show_folder,
)
from qe_studio.ui.widgets.diff_view import diff_key

from viewer_helpers import CTRL, key


@pytest.fixture
def bands(qtbot, main_window, demo_project) -> Path:
    """The grid showing 03_bands, with a second input next to ``bands.in``."""
    folder = demo_project / "03_bands"
    (folder / "bands2.in").write_text((folder / "bands.in").read_text())
    show_folder(qtbot, main_window, folder)
    return folder


@pytest.fixture
def menus(monkeypatch):
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


def test_grid_selects_several_and_the_tree_stays_single(main_window):
    assert (
        main_window.files.view.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    )
    assert (
        main_window.explorer.tree.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
    )


def test_ctrl_and_shift_click_select_and_the_footer_counts(qtbot, main_window, bands):
    window, files = main_window, main_window.files
    click(qtbot, files, "bands.in")
    assert window.status.path.text() == "03_bands/bands.in"
    click(qtbot, files, "bands.out", ctrl=True)
    click(qtbot, files, "scf.out", ctrl=True)
    assert [p.name for p in files.selected_paths()] == ["bands.in", "bands.out", "scf.out"]
    assert window.status.path.text() == "3 itens selecionados"
    click(qtbot, files, "bands.out", ctrl=True)  # toggles it off
    assert window.status.path.text() == "2 itens selecionados"
    click(qtbot, files, "bands.in")  # a plain click goes back to one
    assert window.status.path.text() == "03_bands/bands.in"
    click(qtbot, files, "bands.out", shift=True)  # range from bands.in
    assert len(files.selected_paths()) >= 2


def test_ctrl_a_never_selects_the_up_entry(qtbot, main_window, bands):
    files = main_window.files
    files.view.setFocus()
    key(qtbot, files.view, "A", CTRL)
    reset_modifiers(qtbot, files.view.viewport())
    selected = files.selected_paths()
    assert bands / "bands.in" in selected and len(selected) == len(rows(files)) - 1
    assert not any(files.proxy.is_up(i) for i in files.view.selectionModel().selectedIndexes())
    click(qtbot, files, "bands.in")
    click(qtbot, files, "bands.out", ctrl=True)
    up = rows(files)[0]
    assert files.proxy.is_up(up)
    files.view.selectionModel().select(up, files.view.selectionModel().SelectionFlag.Select)
    assert not files.view.selectionModel().isSelected(up)  # taken out again


def test_menu_of_three_items(main_window, bands, menus):
    files = main_window.files
    paths = select_names(files, "bands.in", "bands.out", "scf.out")
    main_window._show_item_menu(paths, QPoint())
    menu = menus[0]
    assert menu_texts(menu) == ["3 itens", "Abrir local de origem", "Copiar"]
    assert not menu.actions()[0].isEnabled()  # a title, not an action


def test_copy_puts_every_item_on_the_clipboard(main_window, bands, menus):
    paths = select_names(main_window.files, "bands.in", "bands.out", "scf.out")
    main_window._show_item_menu(paths, QPoint())
    next(a for a in menus[0].actions() if a.text() == "Copiar").trigger()
    data = QApplication.clipboard().mimeData()
    assert [url.toLocalFile() for url in data.urls()] == [str(p) for p in paths]
    assert data.text() == "\n".join(str(p) for p in paths)
    gnome = bytes(data.data("x-special/gnome-copied-files")).decode()
    assert gnome == "copy\n" + "\n".join(p.as_uri() for p in paths)
    assert main_window.status.message.text() == "Copiados: 3 itens"


def test_reveal_shows_every_item(main_window, bands, menus, monkeypatch):
    asked = []
    actions = main_window.item_actions
    monkeypatch.setattr(actions, "_show_items_dbus", lambda p: asked.append(p) or True)
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: asked.append(url)))
    paths = select_names(main_window.files, "bands.in", "scf.out")
    main_window._show_item_menu(paths, QPoint())
    next(a for a in menus[0].actions() if a.text() == "Abrir local de origem").trigger()
    assert asked == [paths]


def test_compare_needs_exactly_two_inputs(qtbot, main_window, bands, menus):
    window, files = main_window, main_window.files
    first, second = bands / "bands.in", bands / "bands2.in"
    window._show_item_menu(select_names(files, "bands.in", "bands.out"), QPoint())  # input + output
    window._show_item_menu(select_names(files, "bands.in", "bands2.in", "bands.out"), QPoint())
    window._show_item_menu(select_names(files, "bands.out", "scf.out"), QPoint())  # two outputs
    assert all("Comparar" not in menu_texts(menu) for menu in menus)

    window.set_panel_visible("workspace", False)
    window._show_item_menu(select_names(files, "bands2.in", "bands.in"), QPoint())
    menu = menus[-1]
    assert menu_texts(menu) == ["2 itens", "Abrir local de origem", "Copiar", "Comparar"]
    next(a for a in menu.actions() if a.text() == "Comparar").trigger()
    assert window.workspace.widget_for(diff_key(first, second)) is not None  # path order
    assert not window.workspace.isHidden()


def test_a_folder_is_not_an_input(qtbot, main_window, bands, menus):
    (bands / "sub").mkdir()
    qtbot.waitUntil(
        lambda: any(
            p.name == "sub" for p in map(main_window.files.proxy.path, rows(main_window.files))
        )
    )
    paths = select_names(main_window.files, "bands.in", "sub")
    main_window._show_item_menu(paths, QPoint())
    assert "Comparar" not in menu_texts(menus[0])


def test_right_click_outside_the_selection_replaces_it(qtbot, main_window, bands, menus):
    files = main_window.files
    emitted = []
    files.item_menu_requested.connect(lambda paths, pos: emitted.append(paths))
    select_names(files, "bands.in", "bands.out", "scf.out")

    def at(name):
        return files.view.visualRect(index_of(files, name)).center()

    files._on_context_menu(at("bands.out"))  # inside: the whole selection
    assert [p.name for p in emitted[-1]] == ["bands.in", "bands.out", "scf.out"]
    files._on_context_menu(at("bands2.in"))  # outside: only that item, now the selection
    assert emitted[-1] == [bands / "bands2.in"]
    assert files.selected_paths() == [bands / "bands2.in"]
    files._on_context_menu(files.view.visualRect(rows(files)[0]).center())  # ".." has no menu
    assert len(emitted) == 2


def test_enter_opens_every_selected_file_and_skips_folders(qtbot, main_window, bands):
    window, files = main_window, main_window.files
    (bands / "sub").mkdir()
    qtbot.waitUntil(lambda: any(p.name == "sub" for p in map(files.proxy.path, rows(files))))
    paths = select_names(files, "bands.in", "bands2.in", "sub")
    files.view.setFocus()
    qtbot.keyClick(files.view, Qt.Key.Key_Return)
    opened = {p.name: window.workspace.widget_for(str(p)) is not None for p in paths}
    assert opened == {"sub": False, "bands.in": True, "bands2.in": True}


def test_enter_on_one_item_still_activates_it(qtbot, main_window, bands):
    files = main_window.files
    select_names(files, "bands.in")
    files.view.setCurrentIndex(index_of(files, "bands.in"))
    files.view.setFocus()
    qtbot.keyClick(files.view, Qt.Key.Key_Return)
    assert main_window.workspace.widget_for(str(bands / "bands.in")) is not None


def test_many_files_ask_first(qtbot, main_window, bands, monkeypatch):
    window, files = main_window, main_window.files
    for n in range(12):
        (bands / f"note{n:02d}.txt").write_text("x")
    qtbot.waitUntil(
        lambda: sum(p.suffix == ".txt" for p in map(files.proxy.path, rows(files))) == 12
    )
    paths = select_names(files, *[f"note{n:02d}.txt" for n in range(12)])
    asked = []
    answers = [False, True]
    monkeypatch.setattr(
        "qe_studio.ui.main_window.ask_open_many",
        lambda parent, n: asked.append(n) or answers.pop(0),
    )
    window.open_files(paths)
    assert asked == [12] and window.workspace.widget_for(str(paths[0])) is None
    window.open_files(paths)
    assert asked == [12, 12] and all(window.workspace.widget_for(str(p)) for p in paths)
    asked.clear()
    window.open_files(paths[:10])  # up to ten: no question
    assert asked == []
