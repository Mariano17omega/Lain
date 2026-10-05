"""Spec 31: the "Projeto" dropdown and what it narrows (tree, grid, breadcrumb, sections, palette)."""

import shutil
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMessageBox

from grid_helpers import names, show_folder, tree_names
from project_helpers import ALL, CREATE, config_of, current_text, pick
from qe_studio.core.projects import ProjectError
from qe_studio.ui import project_controller
from qe_studio.ui.focus_controller import focus_chain


@pytest.fixture
def open_window(qtbot, window_factory, raiz):
    """A window on ``raiz`` (or another root) once its first list of projects has arrived."""

    def make(root: Path | None = None, wait: bool = True):
        window = window_factory(config_of(root or raiz))
        if wait:
            qtbot.waitUntil(lambda: window.project.names != [], timeout=5000)
        return window

    return make


# -- the dropdown ---------------------------------------------------------------------------------
def test_the_dropdown_lists_the_projects_of_the_root(open_window):
    window = open_window()
    assert window.project.names == ["ilita", "outro"]  # not plots, not .oculta, not the file
    assert window.explorer.projects.texts() == [ALL, "ilita", "outro", CREATE]
    assert current_text(window) == ALL
    assert window.project.project is None
    assert window.explorer.projects.combo.accessibleName() == "Projeto"


def test_all_projects_is_how_it_was_before(qtbot, open_window, raiz):
    window = open_window()
    assert window.explorer.root == raiz and window.project.view_root == raiz
    qtbot.waitUntil(lambda: tree_names(window) == ["ilita", "outro", "plots", "solto.txt"])
    assert window.windowTitle().endswith(f"[Raiz: {raiz}]")


def test_a_project_narrows_the_tree_to_its_folders(qtbot, open_window, raiz):
    window = open_window()
    pick(window, "ilita")
    assert window.project.project == "ilita"
    assert window.explorer.root == raiz / "ilita"
    # nothing of "outro", no loose file (the model reads the folder in its own thread)
    qtbot.waitUntil(lambda: tree_names(window) == ["Analise_1", "Analise_2"], timeout=5000)
    window.explorer.select_path(raiz / "ilita" / "Analise_1" / "Bandas")  # at any depth
    assert window.explorer.current_path() == raiz / "ilita" / "Analise_1" / "Bandas"
    assert window.windowTitle().endswith("[Projeto: ilita]")
    assert window.project.view_root == raiz / "ilita"


def test_choosing_a_project_selects_its_folder_like_a_click(qtbot, open_window, raiz):
    window = open_window()
    show_folder(qtbot, window, raiz / "outro" / "Analise_1", up=True)
    pick(window, "ilita")
    assert window.files.folder == raiz / "ilita"
    assert window.navigation.history.current == raiz / "ilita"
    assert window.navigation.history.can_back  # the history is kept
    assert window._actions["sync.start"].text() == "Sincronizar ilita"


def test_the_grid_stops_at_the_project(qtbot, open_window, raiz):
    window = open_window()
    pick(window, "ilita")
    show_folder(qtbot, window, raiz / "ilita", up=False)
    assert names(window.files) == ["Analise_1", "Analise_2"]  # no ".." above the project
    folders = []
    window.files.folder_activated.connect(folders.append)
    window.files.go_up()
    assert folders == []
    show_folder(qtbot, window, raiz / "ilita" / "Analise_1")
    assert names(window.files)[0] == ".."
    window.files.go_up()
    assert folders == [raiz / "ilita"]


def test_the_breadcrumb_starts_at_the_project(qtbot, open_window, raiz):
    window = open_window()
    crumb = window.top_bar.breadcrumb
    pick(window, "ilita")
    assert crumb.visible_names() == ["ilita"]
    window.explorer.select_path(raiz / "ilita" / "Analise_1")
    assert [s.path for s in crumb.segments] == [raiz / "ilita", raiz / "ilita" / "Analise_1"]
    assert crumb.visible_names()[0] == "ilita"
    pick(window, ALL)
    assert crumb.visible_names() == [raiz.name]


def test_favorites_and_recents_show_only_the_project(qtbot, open_window, raiz):
    window = open_window()
    window.navigation.set_favorite(raiz / "ilita" / "Analise_1", True)
    window.navigation.set_favorite(raiz / "outro" / "Analise_1", True)
    assert window.explorer.favorites.labels() == ["ilita/Analise_1", "outro/Analise_1"]
    pick(window, "ilita")
    assert window.explorer.favorites.labels() == ["Analise_1"]
    assert [e.path for e in window.explorer.favorites.entries] == [raiz / "ilita" / "Analise_1"]
    assert all(e.path.is_relative_to(raiz / "ilita") for e in window.explorer.recents.entries)
    pick(window, ALL)  # the others were only out of sight
    assert window.explorer.favorites.labels() == ["ilita/Analise_1", "outro/Analise_1"]


def test_the_palette_lists_the_folders_of_the_project(qtbot, open_window, raiz):
    window = open_window()
    window.navigation.set_favorite(raiz / "outro" / "Analise_1", True)
    window.command_palette._ensure_index()
    qtbot.waitUntil(lambda: window.command_palette._folders is not None, timeout=5000)

    def folders(query):
        return [
            r.key for r in window.command_palette.rows_for(query) if r.key.startswith("folder:")
        ]

    assert f"folder:{raiz / 'outro' / 'Analise_1'}" in folders("/analise")
    pick(window, "ilita")
    found = folders("/analise")
    assert found and all(f"folder:{raiz / 'ilita'}" in key for key in found)
    assert f"folder:{raiz / 'outro' / 'Analise_1'}" not in folders("")  # nor as a favorite
    labels = {r.label for r in window.command_palette.rows_for("/analise")}
    assert "Analise_1/Bandas" in labels  # relative to the project, not to the root
    assert not any(label.startswith("ilita/") for label in labels)
    assert "action:calc.create" in [r.key for r in window.command_palette.rows_for(">")]


# -- the choice is kept ---------------------------------------------------------------------------
def test_the_choice_comes_back_after_a_restart(qtbot, window_factory, open_window, raiz):
    window = open_window()
    pick(window, "outro")
    window.close()
    again = window_factory(config_of(raiz))
    qtbot.waitUntil(lambda: again.project.names != [])
    assert again.project.project == "outro"
    assert again.explorer.root == raiz / "outro" and current_text(again) == "outro"
    qtbot.waitUntil(lambda: tree_names(again) == ["Analise_1"], timeout=5000)


def test_a_project_that_is_gone_falls_back_to_all(qtbot, window_factory, open_window, raiz):
    window = open_window()
    pick(window, "ilita")
    window.close()
    shutil.rmtree(raiz / "ilita")
    again = window_factory(config_of(raiz))
    with qtbot.waitSignal(again.project.listed, timeout=5000):
        pass
    assert again.project.project is None and current_text(again) == ALL
    assert again.explorer.root == raiz
    assert again.status.message.text() == "Projeto ilita não encontrado"
    assert again.settings.value("explorer/project", "x", type=str) == ""


def test_the_list_is_read_again_by_f5(qtbot, open_window, raiz):
    window = open_window()
    (raiz / "terceiro").mkdir()
    with qtbot.waitSignal(window.project.listed, timeout=5000):
        window.refresh()
    assert window.explorer.projects.texts() == [ALL, "ilita", "outro", "terceiro", CREATE]


def test_the_dropdown_is_off_without_a_root_folder(open_window, tmp_path):
    window = open_window(tmp_path / "gone", wait=False)
    assert window.first_run.state == "missing_root"
    assert not window.explorer.projects.isEnabled()
    assert window.explorer.projects.texts() == [ALL, CREATE]


# -- going somewhere else -------------------------------------------------------------------------
def test_going_back_into_another_project_switches_to_it(qtbot, open_window, raiz):
    window = open_window()
    pick(window, "ilita")
    window.explorer.select_path(raiz / "ilita" / "Analise_1")
    window.navigation.go_to(raiz / "outro" / "Analise_1")  # a link from elsewhere
    assert window.project.project == "outro" and current_text(window) == "outro"
    assert window.explorer.root == raiz / "outro"
    assert window.files.folder == raiz / "outro" / "Analise_1"
    assert window.navigation.history.current == raiz / "outro" / "Analise_1"
    window.navigation.back()  # the history was not cleared: back to the first project
    assert window.project.project == "ilita" and current_text(window) == "ilita"
    assert window.files.folder == raiz / "ilita" / "Analise_1"
    window.navigation.back()
    assert window.files.folder == raiz / "ilita"


def test_a_folder_on_the_root_itself_switches_to_all(qtbot, open_window, raiz):
    window = open_window()
    pick(window, "ilita")
    window.explorer.select_path(raiz)
    assert window.project.project is None and current_text(window) == ALL
    assert window.files.folder == raiz


def test_reveal_in_explorer_follows_the_file_to_its_project(qtbot, open_window, raiz):
    window = open_window()
    pick(window, "ilita")
    window.reveal_in_explorer(raiz / "outro" / "Analise_1" / "Relax")
    assert window.project.project == "outro"
    assert window.explorer.current_path() == raiz / "outro" / "Analise_1" / "Relax"


def test_a_path_outside_the_root_is_left_alone(open_window, raiz, tmp_path):
    window = open_window()
    pick(window, "ilita")
    window.explorer.select_path(tmp_path)
    assert window.project.project == "ilita" and window.explorer.root == raiz / "ilita"


def test_renaming_the_selected_project_follows_it(qtbot, open_window, raiz, monkeypatch):
    window = open_window()
    pick(window, "ilita")
    monkeypatch.setattr("qe_studio.ui.rename_controller.ask_rename", lambda parent, path: "ilita2")
    with qtbot.waitSignal(window.project.listed, timeout=5000):
        window.rename_path(raiz / "ilita")
    assert window.project.project == "ilita2" and current_text(window) == "ilita2"
    assert window.explorer.root == raiz / "ilita2"
    assert window.project.names == ["ilita2", "outro"]


def test_a_config_reload_keeps_the_project_of_the_same_root(qtbot, open_window, raiz, tmp_path):
    window = open_window()
    pick(window, "outro")
    window._apply_loaded(config_of(raiz))
    assert window.project.project == "outro"
    assert window.explorer.root == raiz / "outro" and window.files.folder == raiz / "outro"
    elsewhere = tmp_path / "outra_raiz"
    (elsewhere / "p1").mkdir(parents=True)
    window.use_session_root(elsewhere)  # another root starts on "Todos"
    assert window.project.project is None and window.explorer.root == elsewhere
    qtbot.waitUntil(lambda: window.project.names == ["p1"])
    assert window.explorer.projects.texts() == [ALL, "p1", CREATE]


# -- "Criar projeto…" -----------------------------------------------------------------------------
def test_creating_a_project(qtbot, open_window, raiz, monkeypatch):
    window = open_window()
    asked = []
    monkeypatch.setattr(
        project_controller,
        "ask_new_project",
        lambda parent, existing, hidden=(): asked.append(list(existing)) or "novo",
    )
    with qtbot.waitSignal(window.project.created, timeout=5000):
        pick(window, CREATE)
    assert asked == [["ilita", "outro"]]
    assert (raiz / "novo").is_dir() and list((raiz / "novo").iterdir()) == []
    assert window.project.project == "novo" and current_text(window) == "novo"
    assert window.explorer.root == raiz / "novo"
    assert window.files.folder == raiz / "novo"
    assert window.toast.current is not None
    assert (window.toast.current.level, window.toast.current.text) == (
        "success",
        "Projeto novo criado",
    )
    qtbot.waitUntil(lambda: "novo" in window.project.names)
    assert window.explorer.projects.texts() == [ALL, "ilita", "novo", "outro", CREATE]
    assert window.plot_workflow.busy.labels == []


def test_the_menu_action_creates_a_project_too(qtbot, open_window, raiz, monkeypatch):
    window = open_window()
    monkeypatch.setattr(project_controller, "ask_new_project", lambda *args: "via-menu")
    action = window._actions["project.create"]
    assert action.text() == "Criar projeto…" and action.isEnabled()
    with qtbot.waitSignal(window.project.created, timeout=5000):
        action.trigger()
    assert (raiz / "via-menu").is_dir()
    assert "action:project.create" in [r.key for r in window.command_palette.rows_for(">criar")]


def test_cancelling_creates_nothing_and_restores_the_selection(open_window, raiz, monkeypatch):
    window = open_window()
    pick(window, "ilita")
    monkeypatch.setattr(project_controller, "ask_new_project", lambda *args: None)
    pick(window, CREATE)
    assert current_text(window) == "ilita" and window.project.project == "ilita"
    assert sorted(p.name for p in raiz.iterdir() if p.is_dir()) == [
        ".oculta",
        "ilita",
        "outro",
        "plots",
    ]


def test_a_failed_creation_says_why_and_keeps_the_selection(qtbot, open_window, monkeypatch):
    window = open_window()
    boxes = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text: boxes.append((title, text))),
    )
    monkeypatch.setattr(project_controller, "ask_new_project", lambda *args: "novo")

    def refuse(root, name, hidden=()):
        raise ProjectError("Já existe uma pasta com esse nome")

    monkeypatch.setattr(project_controller, "create_project", refuse)
    with qtbot.waitSignal(window.project.failed, timeout=5000):
        pick(window, CREATE)
    assert boxes == [("Criar projeto", "Já existe uma pasta com esse nome")]
    assert current_text(window) == ALL and window.project.project is None
    assert window.plot_workflow.busy.labels == []


def test_closing_the_window_cancels_the_list(open_window):
    window = open_window()
    window.refresh()
    window.close()
    assert window.project._tasks.active("projects:list") is None


def test_the_dropdown_is_in_the_explorer_region_before_the_tree(main_window):
    """The combo is reached by Tab right after the explorer's buttons, before its tree."""
    window = main_window
    window.focus_areas.apply_tab_order()
    explorer = window.focus_areas.regions[2]
    combo = window.explorer.projects.combo
    assert explorer.isAncestorOf(combo)
    chain = [w for w in focus_chain(window.explorer.projects.combo) if explorer.isAncestorOf(w)]
    assert chain.index(combo) < chain.index(window.explorer.tree)
