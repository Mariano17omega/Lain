"""Spec 31 R5, R6: what a selected project changes in sync, push and "Criar cálculo"."""

import pytest
from PyQt6.QtCore import QPoint

from project_helpers import ALL, current_text, pick
from qe_studio.core.calc_create.preview import AT_ROOT
from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.sync.request import PUSH_PROJECT, PUSH_ROOT
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


@pytest.fixture
def cluster_window(qtbot, window_factory, raiz):
    """A window with sync on over ``raiz``; its monitor probes a closed port."""
    data = {
        "paths": {"local_root": str(raiz), "remote_root": "/scratch/me"},
        "cluster": {"host": "127.0.0.1", "port": 9, "user": "me"},
    }
    window = window_factory(LoadedConfig(parse_config(data), None))
    qtbot.waitUntil(lambda: window.project.names != [], timeout=5000)
    return window


# -- sync (R5.1) ----------------------------------------------------------------------------------
def test_sync_project_follows_the_selected_project(cluster_window, raiz):
    window = cluster_window
    action = window._actions["sync.project"]
    runs = []
    window.sync.run = lambda folder, endpoint, password=None: runs.append((folder, endpoint.path))
    assert action.text() == "Sincronizar tudo" and "tudo" in action.toolTip()

    pick(window, "ilita")
    assert action.text() == "Sincronizar projeto ilita"
    assert action.toolTip() == "Baixar do cluster: projeto ilita"
    window.explorer.select_path(raiz / "ilita" / "Analise_1")  # whatever is selected
    action.trigger()
    assert runs == [(raiz / "ilita", "/scratch/me/ilita")]  # the remote mapping did not change

    pick(window, ALL)
    assert action.text() == "Sincronizar tudo"
    action.trigger()
    assert runs[-1] == (raiz, "/scratch/me")


def test_the_rsync_button_says_the_scope_of_the_project_folder(cluster_window, raiz):
    window = cluster_window
    pick(window, "ilita")
    assert window.activity.rsync.toolTip() == "Baixar do cluster: ilita (e subpastas)"
    window.explorer.select_path(raiz / "ilita" / "Analise_1")
    assert window._actions["sync.start"].text() == "Sincronizar ilita/Analise_1"


def test_a_config_reload_forgets_the_project_scope_of_sync(cluster_window, raiz):
    window = cluster_window
    pick(window, "ilita")
    window._apply_loaded(window.loaded)  # the same root: the project stays, sync is told again
    assert window._actions["sync.project"].text() == "Sincronizar projeto ilita"


# -- push (R5.2) ----------------------------------------------------------------------------------
def test_a_project_folder_is_not_pushed(cluster_window, raiz, monkeypatch):
    window = cluster_window
    shown = []
    monkeypatch.setattr("PyQt6.QtWidgets.QMenu.exec", lambda menu, pos: shown.append(menu))
    action = window._actions["sync.push"]
    pick(window, "ilita")  # the project's folder is the current one now
    assert not action.isEnabled() and action.toolTip() == PUSH_PROJECT
    window._show_item_menu([raiz / "ilita"], QPoint())
    item = next(a for a in shown[-1].actions() if a.text() == "Enviar ao cluster")
    assert not item.isEnabled() and item.toolTip() == PUSH_PROJECT
    window.explorer.select_path(raiz / "ilita" / "Analise_1")  # a calculation folder: fine
    assert action.isEnabled()
    pick(window, ALL)
    assert not action.isEnabled() and action.toolTip() == PUSH_ROOT


# -- "Criar cálculo" (R6.2) -----------------------------------------------------------------------
def test_the_default_place_is_the_selected_project(cluster_window, raiz):
    window = cluster_window
    pick(window, "ilita")
    window.calc_create.open()
    dialog = window.calc_create.dialog
    assert dialog is not None
    try:
        assert dialog.setup.location == raiz / "ilita"
        assert AT_ROOT not in dialog.setup.location_message.text()
    finally:
        dialog.close()


def test_without_a_project_the_default_place_is_the_root_and_it_warns(cluster_window, raiz):
    window = cluster_window
    assert current_text(window) == ALL
    window.calc_create.open()
    dialog = window.calc_create.dialog
    assert dialog is not None
    try:
        assert dialog.setup.location == raiz
        assert AT_ROOT in dialog.setup.location_message.text()
    finally:
        dialog.close()
