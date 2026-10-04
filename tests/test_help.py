"""Spec 18 R1: the Ajuda menu, the shortcuts dialog, "Sobre o Lain", the log and the data folder."""

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMenu

from qe_studio import APP_NAME, __version__
from qe_studio.core.appdirs import data_dir, log_path
from qe_studio.ui.dialogs import about as about_module
from qe_studio.ui.dialogs.shortcuts import pretty_keys
from qe_studio.ui.widgets.explorer import ExplorerPanel
from qe_studio.ui.widgets.file_grid import FilePanel
from qe_studio.ui.widgets.text_viewer import TextViewer
from qe_studio.ui.widgets.workspace import Workspace

HELP_ITEMS = [
    "Atalhos de teclado",
    "Paleta de comandos",
    "Abrir log",
    "Abrir pasta de dados",
    "Sobre o Lain",
]


def menu_titles(window) -> list[str]:
    return [a.text().replace("&", "") for a in window.menuBar().actions()]


def rows_of(window) -> list[tuple[str, str, str]]:
    return window.help.shortcut_rows()


def open_shortcuts(window):
    window._actions["help.shortcuts"].trigger()
    assert window.help.dialog is not None
    return window.help.dialog


def test_help_is_the_last_menu_with_its_five_items(main_window):
    titles = menu_titles(main_window)
    assert titles[-1] == "Ajuda"
    menu = main_window.menuBar().actions()[-1].menu()
    assert isinstance(menu, QMenu)
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == HELP_ITEMS
    assert main_window._actions["help.shortcuts"].shortcut().toString() == "F1"
    assert main_window._actions["help.palette"].shortcut().toString() == "Ctrl+K"


def test_shortcut_rows_cover_actions_and_widgets(main_window):
    flat = {(keys, where) for _action, keys, where in rows_of(main_window)}
    keys = {k for k, _where in flat}
    for expected in ("Ctrl+G", "Ctrl+E", "Ctrl+T", "F5", "Ctrl+K", "F1", "Alt+Left", "Alt+Right"):
        assert expected in keys, expected
    assert {"Backspace", "Alt+↑", "Ctrl+F", "F3", "Ctrl+L", "Ctrl+Home", "F8"} <= keys
    assert ("Ctrl+F", "Grade de arquivos") in flat
    assert ("Ctrl+F", "Visualizador de texto") in flat
    assert ("Ctrl+F", "Árvore de pastas") in flat
    # Each shortcut once per place: the registry's Alt+←/→ and Ctrl+W are not repeated by widgets.
    assert len(rows_of(main_window)) == len(set(rows_of(main_window)))
    assert sum(1 for _a, k, _w in rows_of(main_window) if k == "Ctrl+W") == 1


def test_the_widgets_declare_their_own_shortcuts(main_window):
    for provider in (
        ExplorerPanel.shortcut_help,
        FilePanel.shortcut_help,
        TextViewer.shortcut_help,
        Workspace.shortcut_help,
        main_window.navigation.shortcut_help,
    ):
        rows = provider()
        assert rows and all(
            len(row) == 3 and all(isinstance(c, str) and c for c in row) for row in rows
        )


def test_text_viewer_help_is_its_registered_shortcuts(qtbot, main_window, demo_project):
    from viewer_helpers import open_text

    viewer = open_text(qtbot, main_window, demo_project / "03_bands" / "bands.in")
    registered = {s.key().toString() for s in viewer._shortcuts.values()}
    assert {keys for _what, keys, _where in TextViewer.shortcut_help()} == registered


def test_the_dialog_lists_the_keys_and_is_not_modal(qtbot, main_window):
    dialog = open_shortcuts(main_window)
    qtbot.addWidget(dialog)
    shown = dialog.visible_rows()
    keys = {k for _a, k, _w in shown}
    assert {"Ctrl+G", "Ctrl+E", "Ctrl+T", "F5", "Ctrl+K", "Alt+←", "Alt+→", "Backspace"} <= keys
    assert dialog.windowTitle() == "Atalhos de teclado"
    assert not dialog.isModal() and dialog.isVisible()
    # Asking again brings the same window forward instead of opening a second one.
    main_window._actions["help.shortcuts"].trigger()
    assert main_window.help.dialog is dialog


def test_the_dialog_search_ignores_case_and_accents(qtbot, main_window):
    dialog = open_shortcuts(main_window)
    qtbot.addWidget(dialog)
    dialog.search.setText("GRADE")
    where = {w for _a, _k, w in dialog.visible_rows()}
    assert where == {"Grade de arquivos"}
    dialog.search.setText("arvore")  # "Árvore de pastas"
    assert [w for _a, _k, w in dialog.visible_rows()] == ["Árvore de pastas"]
    dialog.search.setText("backspace")
    assert [k for _a, k, _w in dialog.visible_rows()] == ["Backspace"]
    dialog.search.setText("nada disso existe")
    assert dialog.visible_rows() == []


def test_closing_the_dialog_lets_the_next_request_open_a_new_one(qtbot, main_window):
    first = open_shortcuts(main_window)
    first.close()
    qtbot.waitUntil(lambda: main_window.help.dialog is None, timeout=3000)
    assert open_shortcuts(main_window) is not first


def test_pretty_keys():
    assert pretty_keys("Alt+Left") == "Alt+←"
    assert pretty_keys("Ctrl+Home") == "Ctrl+Home"
    assert pretty_keys("Botão do meio") == "Botão do meio"


# -- Sobre o Lain -----------------------------------------------------------------------------
def test_about_rows_have_versions_and_paths(main_window):
    rows = dict(main_window.help.about_rows())
    assert rows[APP_NAME] == __version__
    for name in ("Python", "Qt", "PyQt", "matplotlib", "numpy", "ASE"):
        assert rows[name] and rows[name] != "não instalado", name
    assert rows["Config"] == "nenhum"
    assert rows["Log"] == str(log_path())
    assert rows["Dados"] == str(data_dir())


def test_about_dialog_copies_the_information(qtbot, main_window, monkeypatch):
    shown = []
    monkeypatch.setattr(about_module.AboutDialog, "exec", lambda self: shown.append(self) or 0)
    main_window.help.show_about()
    assert len(shown) == 1
    dialog = shown[0]
    qtbot.addWidget(dialog)
    dialog.copy_button.click()
    text = QApplication.clipboard().text()
    assert f"{__version__}" in text and str(log_path()) in text
    assert "Config: nenhum" in text
    assert text == dialog.info_text()


def test_about_does_not_import_ase():
    # Versions come from the package metadata: opening the dialog must not load ASE (spec 14).
    import subprocess
    import sys

    code = (
        "import sys; from qe_studio.core.about import package_versions; package_versions();"
        "sys.exit(1 if 'ase' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


# -- log and data folder ----------------------------------------------------------------------
def test_open_log_opens_the_log_in_a_text_tab(qtbot, main_window):
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("2026-10-04 INFO qe_studio: hello\n", encoding="utf-8")
    main_window._actions["help.log"].trigger()
    viewer = main_window.workspace.widget_for(str(path))
    assert isinstance(viewer, TextViewer)
    assert main_window.workspace.isVisible()


def test_open_log_without_a_log_says_so(main_window):
    assert not log_path().exists()
    main_window._actions["help.log"].trigger()
    assert str(log_path()) in main_window.status.message.text()
    assert main_window.workspace.widget_for(str(log_path())) is None


def test_open_data_dir_asks_the_desktop(main_window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(opened.append))
    main_window._actions["help.data"].trigger()
    assert opened == [QUrl.fromLocalFile(str(data_dir()))]
    assert data_dir().is_dir()


@pytest.mark.parametrize(
    "name", ["help.shortcuts", "help.palette", "help.log", "help.data", "help.about"]
)
def test_every_help_action_is_registered(main_window, name):
    assert name in main_window._actions
