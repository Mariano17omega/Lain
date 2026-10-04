"""Spec 10 R5: tab context menu, middle-click close and Ctrl+W."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from qe_studio.core.plotting.plot_file import read_plot_file


@pytest.fixture
def three_tabs(qtbot, main_window, tmp_path):
    """Tabs a.txt, b.txt, c.txt (text viewers) and their paths."""
    paths = []
    for name in "abc":
        path = tmp_path / f"{name}.txt"
        path.write_text(f"{name}\n")
        main_window.open_file(path)
        paths.append(path)
    return main_window, paths


def titles(window) -> list[str]:
    tabs = window.workspace.tabs
    return [tabs.tabText(i) for i in range(tabs.count())]


@pytest.fixture
def menu_choice(monkeypatch):
    """Patch ``QMenu.exec`` to trigger the entry set in ``choice[0]``; ``shown`` records the
    menus: ``[(text, enabled)]`` of each."""
    choice, shown = [None], []

    def run(menu, pos):
        entries = [(a.text().split("\t")[0], a.isEnabled()) for a in menu.actions() if a.text()]
        shown.append(entries)
        if choice[0] is not None:
            next(a for a in menu.actions() if a.text().split("\t")[0] == choice[0]).trigger()

    monkeypatch.setattr(QMenu, "exec", run)
    return choice, shown


def test_tab_menu_entries(qtbot, three_tabs, menu_choice):
    window, _paths = three_tabs
    _choice, shown = menu_choice
    window.workspace.tabs.bar.menu_requested.emit(0, QPoint())
    window.workspace.tabs.bar.menu_requested.emit(2, QPoint())
    names = [
        "Fechar",
        "Fechar outras",
        "Fechar à direita",
        "Fechar todas",
        "Copiar caminho",
        "Revelar no explorador",
    ]
    assert [n for n, _e in shown[0]] == names
    assert dict(shown[0])["Fechar à direita"] and not dict(shown[1])["Fechar à direita"]


def test_right_click_on_a_tab_opens_the_menu(qtbot, three_tabs, menu_choice):
    window, _paths = three_tabs
    _choice, shown = menu_choice
    bar = window.workspace.tabs.bar
    pos = bar.tabRect(1).center()
    QApplication.sendEvent(
        bar, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, bar.mapToGlobal(pos))
    )
    assert len(shown) == 1
    empty = bar.tabRect(2).right() + 400  # past the last tab: no menu
    QApplication.sendEvent(
        bar,
        QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(empty, 5), QPoint(empty, 5)),
    )
    assert len(shown) == 1


def test_close_others_keeps_the_chosen_tab(qtbot, three_tabs, menu_choice):
    window, _paths = three_tabs
    menu_choice[0][0] = "Fechar outras"
    window.workspace.tabs.bar.menu_requested.emit(1, QPoint())
    assert titles(window) == ["b.txt"]
    assert window.workspace.current() is window.workspace.tabs.widget(0)


def test_close_to_the_right_follows_the_visual_order(qtbot, three_tabs, menu_choice):
    window, _paths = three_tabs
    tabs = window.workspace.tabs
    tabs.bar.moveTab(0, 2)  # now b, c, a
    assert titles(window) == ["b.txt", "c.txt", "a.txt"]
    menu_choice[0][0] = "Fechar à direita"
    tabs.bar.menu_requested.emit(0, QPoint())
    assert titles(window) == ["b.txt"]


def test_close_all_and_close_one(qtbot, three_tabs, menu_choice):
    window, _paths = three_tabs
    choice, _shown = menu_choice
    closing = []
    window.workspace.tab_closing.connect(closing.append)
    choice[0] = "Fechar"
    window.workspace.tabs.bar.menu_requested.emit(0, QPoint())
    assert titles(window) == ["b.txt", "c.txt"]
    choice[0] = "Fechar todas"
    window.workspace.tabs.bar.menu_requested.emit(0, QPoint())
    assert window.workspace.current() is None and len(closing) == 3
    assert window.workspace.keys() == []


def test_copy_path_and_reveal(qtbot, three_tabs, menu_choice):
    window, paths = three_tabs
    choice, _shown = menu_choice
    choice[0] = "Copiar caminho"
    window.workspace.tabs.bar.menu_requested.emit(1, QPoint())
    assert QApplication.clipboard().text() == str(paths[1])
    asked = []
    window.workspace.reveal_requested.connect(asked.append)
    choice[0] = "Revelar no explorador"
    window.workspace.tabs.bar.menu_requested.emit(2, QPoint())
    assert asked == [paths[2]]


def test_reveal_selects_the_file_in_the_tree_and_the_grid(
    qtbot, main_window, demo_project, menu_choice
):
    window = main_window
    path = demo_project / "03_bands" / "bands.in"
    window.open_file(path)
    window.set_panel_visible("grid", False)
    window.set_left_mode("params")
    assert window.explorer.current_path() != path
    menu_choice[0][0] = "Revelar no explorador"
    window.workspace.tabs.bar.menu_requested.emit(0, QPoint())
    assert window.explorer.current_path() == path
    assert window.left.currentIndex() == 0 and not window.left.isHidden()  # the tree is shown
    assert not window.files.isHidden()
    qtbot.waitUntil(
        lambda: (
            window.files.folder == path.parent
            and window.files.proxy.path(window.files.view.currentIndex()) == path
        ),
        timeout=5000,
    )


def test_middle_click_closes_the_tab_under_the_cursor(qtbot, three_tabs):
    window, _paths = three_tabs
    bar = window.workspace.tabs.bar
    QTest.mouseClick(
        bar, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, bar.tabRect(1).center()
    )
    assert titles(window) == ["a.txt", "c.txt"]
    QTest.mouseClick(  # empty strip: nothing closes
        bar, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, QPoint(bar.width() - 2, 5)
    )
    assert len(titles(window)) == 2


def test_ctrl_w_closes_the_current_tab(qtbot, three_tabs):
    window, _paths = three_tabs
    assert window.workspace.tabs.currentIndex() == 2
    qtbot.keyClick(window, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    assert titles(window) == ["a.txt", "b.txt"]
    window.workspace.close_all()
    window.workspace.close_current()  # no tabs: nothing happens


def test_closing_a_plot_tab_from_the_menu_saves_its_settings(
    qtbot, main_window, demo_project, menu_choice
):
    window = main_window
    folder = demo_project / "03_bands"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)
    window.params.set_param("emin", -3.0)  # pending: the debounce has not written it yet
    assert not (folder / "bands.plot").exists()
    menu_choice[0][0] = "Fechar todas"
    window.workspace.tabs.bar.menu_requested.emit(0, QPoint())
    assert window.workspace.current() is None
    window.plot_settings.flush_now()  # the tab's write runs in the settings worker
    stored, _ = read_plot_file(folder, "bands")
    assert stored["emin"] == -3.0


def test_plot_tab_path_is_its_folder(qtbot, main_window, demo_project, menu_choice):
    window = main_window
    folder = demo_project / "03_bands"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.generate_plot_for(folder, auto_export=False)
    menu_choice[0][0] = "Copiar caminho"
    window.workspace.tabs.bar.menu_requested.emit(0, QPoint())
    assert Path(QApplication.clipboard().text()) == folder
