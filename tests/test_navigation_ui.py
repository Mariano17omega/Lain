"""Spec 16 R1/R2 in the window: the breadcrumb, Alt+←/→, the side mouse buttons, the history."""

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMenu

from grid_helpers import reset_modifiers


@pytest.fixture
def deep(demo_project) -> Path:
    """``<root>/runs/a/b``, made before the window exists so the models list it at once."""
    folder = demo_project / "runs" / "a" / "b"
    folder.mkdir(parents=True)
    (demo_project / "runs" / "x").mkdir()
    return folder


def go(window, folder: Path) -> None:
    window.explorer.select_path(folder)
    assert window.files.folder == folder and window.current_folder() == folder


def crumb_button(window, text: str):
    breadcrumb = window.top_bar.breadcrumb
    return next(b for b in breadcrumb._buttons if b.text() == text)


def alt(qtbot, widget, key: Qt.Key) -> None:
    qtbot.keyClick(widget, key, Qt.KeyboardModifier.AltModifier)
    reset_modifiers(qtbot, widget)


# -- R1: breadcrumb ------------------------------------------------------------------------------
def test_breadcrumb_has_one_segment_per_level(deep, main_window, demo_project):
    window = main_window
    crumb = window.top_bar.breadcrumb
    assert crumb.visible_names() == [demo_project.name]  # the project is the first segment
    go(window, deep)
    assert [s.path for s in crumb.segments] == [
        demo_project,
        demo_project / "runs",
        demo_project / "runs" / "a",
        deep,
    ]
    assert crumb.visible_names() == [demo_project.name, "runs", "a", "b"]
    assert crumb.toolTip() == str(deep)
    assert crumb_button(window, "a").toolTip() == str(demo_project / "runs" / "a")


def test_clicking_a_segment_navigates_the_tree_and_the_grid(deep, main_window, demo_project):
    window = main_window
    go(window, deep)
    crumb_button(window, "a").click()
    folder = demo_project / "runs" / "a"
    assert window.files.folder == folder and window.explorer.current_path() == folder
    assert window.top_bar.breadcrumb.visible_names()[-1] == "a"
    crumb_button(window, demo_project.name).click()  # the project itself
    assert window.files.folder == demo_project and window.explorer.current_path() is None


def test_narrow_breadcrumb_collapses_the_middle_into_a_menu(deep, main_window, demo_project):
    window = main_window
    go(window, deep)
    crumb = window.top_bar.breadcrumb
    assert crumb.more.isHidden()
    crumb.setFixedWidth(150)
    assert not crumb.more.isHidden()
    names = crumb.visible_names()
    assert names[0] == demo_project.name and names[-1] == "b"  # root and current stay
    hidden = [s.name for s in crumb.hidden_segments()]
    assert hidden and hidden[0] == "runs"  # the levels next to the project go first
    assert [a.text() for a in crumb.more.menu().actions()] == hidden
    crumb.more.menu().actions()[0].trigger()
    assert window.files.folder == demo_project / "runs"
    crumb.setFixedWidth(560)
    assert crumb.more.isHidden() or crumb.hidden_segments() == []


def test_breadcrumb_menu_copies_the_absolute_path(deep, main_window, monkeypatch):
    window = main_window
    go(window, deep)
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: menu.actions()[0].trigger())
    crumb = window.top_bar.breadcrumb
    crumb._on_context_menu(crumb.rect().center())
    assert QApplication.clipboard().text() == str(deep)
    assert window.status.message.text() == f"Copiado: {deep}"


# -- R2: history ---------------------------------------------------------------------------------
def test_alt_arrows_walk_the_history(qtbot, deep, main_window, demo_project):
    window = main_window
    runs, a = demo_project / "runs", demo_project / "runs" / "a"
    bar = window.top_bar
    assert not bar.back_button.isEnabled() and not bar.forward_button.isEnabled()
    go(window, runs)
    go(window, a)
    assert bar.back_button.isEnabled() and not bar.forward_button.isEnabled()
    window.files.view.setFocus()
    alt(qtbot, window.files.view, Qt.Key.Key_Left)
    assert window.files.folder == runs
    alt(qtbot, window.files.view, Qt.Key.Key_Left)
    assert window.files.folder == demo_project and not bar.back_button.isEnabled()
    assert bar.forward_button.isEnabled()
    alt(qtbot, window.files.view, Qt.Key.Key_Right)
    assert window.files.folder == runs
    assert window.top_bar.breadcrumb.visible_names()[-1] == "runs"
    go(window, demo_project / "04_pdos")  # a new folder: "avançar" is gone
    assert not bar.forward_button.isEnabled()
    alt(qtbot, window.files.view, Qt.Key.Key_Right)
    assert window.files.folder == demo_project / "04_pdos"


def test_history_does_not_push_itself(deep, main_window, demo_project):
    window = main_window
    go(window, demo_project / "runs")
    go(window, demo_project / "runs" / "a")
    window.navigation.back()
    window.navigation.back()
    window.navigation.forward()
    assert window.navigation.history.back_stack == [demo_project]
    assert window.navigation.history.forward_stack == [demo_project / "runs" / "a"]


def test_the_buttons_and_the_menu_actions_go_back_and_forward(deep, main_window, demo_project):
    window = main_window
    go(window, demo_project / "runs")
    window.top_bar.back_button.click()
    assert window.files.folder == demo_project
    window.top_bar.forward_button.click()
    assert window.files.folder == demo_project / "runs"
    assert window._actions["nav.back"].shortcut().toString() == "Alt+Left"
    assert window._actions["nav.forward"].shortcut().toString() == "Alt+Right"
    window._actions["nav.back"].trigger()
    assert window.files.folder == demo_project


@pytest.mark.parametrize("panel", ["grid", "tree", "workspace"])
def test_side_mouse_buttons_work_from_any_panel(qtbot, deep, main_window, demo_project, panel):
    window = main_window
    go(window, demo_project / "runs")
    window.open_file(demo_project / "03_bands" / "bands.in")
    target = {
        "grid": window.files.view.viewport(),
        "tree": window.explorer.tree.viewport(),
        "workspace": window.workspace,
    }[panel]
    qtbot.mouseClick(target, Qt.MouseButton.BackButton)
    assert window.files.folder == demo_project
    qtbot.mouseClick(target, Qt.MouseButton.ForwardButton)
    assert window.files.folder == demo_project / "runs"


def test_a_vanished_folder_is_skipped_with_a_message(deep, main_window, demo_project):
    window = main_window
    runs, x = demo_project / "runs", demo_project / "runs" / "x"
    go(window, runs)
    go(window, x)
    go(window, runs / "a")
    shutil.rmtree(x)
    window.navigation.back()  # a ← x is gone → runs
    assert window.files.folder == runs
    assert window.status.message.text() == "Pasta não existe mais: x"
    window.navigation.back()
    assert window.files.folder == demo_project
    window.navigation.forward()
    window.navigation.forward()  # runs → a: x is not in the history any more
    assert window.files.folder == runs / "a"


def test_renaming_a_folder_updates_the_history(deep, main_window, demo_project, monkeypatch):
    window = main_window
    runs = demo_project / "runs"
    go(window, runs)
    go(window, runs / "a")
    monkeypatch.setattr("qe_studio.ui.rename_controller.ask_rename", lambda parent, path: "runs2")
    window.rename_path(runs)
    new = demo_project / "runs2"
    history = window.navigation.history
    assert history.back_stack == [demo_project, new]
    assert history.current == new / "a" == window.current_folder()
    window.navigation.back()
    assert window.files.folder == new


def test_another_project_starts_a_new_history(deep, main_window, demo_project):
    window = main_window
    go(window, demo_project / "runs")
    assert window.navigation.history.can_back
    window.navigation.set_root(demo_project)  # what a config reload does
    assert not window.navigation.history.can_back
    assert not window.top_bar.back_button.isEnabled()
