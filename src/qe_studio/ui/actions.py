"""The window's actions by stable id: menu, text, shortcut and slot (spec 15 R4.6).

One table, so the menus, the shortcuts dialog and the command palette (spec 18) list the same
actions. ``slot`` is
an attribute path on the window (``"sync.check_connection"``: its sync coordinator's method).
"""

from __future__ import annotations

from operator import attrgetter
from typing import NamedTuple

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMainWindow

from ..i18n import _


class ActionSpec(NamedTuple):
    id: str
    menu: str
    text: str
    slot: str
    shortcut: str | None = None
    separator_before: bool = False


MENU_FILE = _("Arquivo")
MENU_NAVIGATE = _("Navegar")
MENU_CLUSTER = _("Cluster")
MENU_PLOTS = _("Gráficos")
MENU_TOOLS = _("Ferramentas")
MENU_HELP = _("Ajuda")


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("files.refresh", MENU_FILE, _("Atualizar"), "refresh", "F5"),
    ActionSpec(
        "files.open_external",
        MENU_FILE,
        _("Abrir pasta no gerenciador de arquivos"),
        "open_folder_externally",
    ),
    ActionSpec("project.create", MENU_FILE, _("Criar projeto…"), "project.open_new"),
    ActionSpec("tabs.close", MENU_FILE, _("Fechar aba"), "workspace.close_current", "Ctrl+W"),
    ActionSpec("app.quit", MENU_FILE, _("Sair"), "close", "Ctrl+Q", separator_before=True),
    ActionSpec("nav.back", MENU_NAVIGATE, _("Voltar"), "navigation.back", "Alt+Left"),
    ActionSpec("nav.forward", MENU_NAVIGATE, _("Avançar"), "navigation.forward", "Alt+Right"),
    ActionSpec(
        "focus.tree",
        MENU_NAVIGATE,
        _("Ir para a árvore"),
        "focus_areas.focus_tree",
        "Ctrl+1",
        separator_before=True,
    ),
    ActionSpec(
        "focus.grid", MENU_NAVIGATE, _("Ir para a grade"), "focus_areas.focus_grid", "Ctrl+2"
    ),
    ActionSpec(
        "focus.workspace",
        MENU_NAVIGATE,
        _("Ir para o workspace"),
        "focus_areas.focus_workspace",
        "Ctrl+3",
    ),
    ActionSpec(
        "focus.params", MENU_NAVIGATE, _("Ir para os ajustes"), "focus_areas.focus_params", "Ctrl+4"
    ),
    # "sync.start" says what it pulls: SyncCoordinator.show_scope renames it on every folder change.
    ActionSpec(
        "sync.start", MENU_CLUSTER, _("Sincronizar pasta selecionada"), "sync.start_selected"
    ),
    # "sync.project" too: "Sincronizar projeto <nome>" with a project selected (spec 31 R5).
    ActionSpec("sync.project", MENU_CLUSTER, _("Sincronizar tudo"), "sync.start_project"),
    # "sync.push" too: "Enviar <pasta> ao cluster…", disabled at the root and at a project (spec 27, 31).
    ActionSpec(
        "sync.push",
        MENU_CLUSTER,
        _("Enviar pasta ao cluster…"),
        "sync.start_push",
        separator_before=True,
    ),
    ActionSpec("sync.test", MENU_CLUSTER, _("Testar conexão"), "sync.check_connection"),
    ActionSpec("plot.generate", MENU_PLOTS, _("Gerar gráfico"), "generate_plot", "Ctrl+G"),
    ActionSpec("plot.export", MENU_PLOTS, _("Exportar gráfico"), "export_plot", "Ctrl+E"),
    ActionSpec("grids.open", MENU_PLOTS, _("Grids…"), "grids.open"),
    ActionSpec("calc.create", MENU_TOOLS, _("Criar cálculo…"), "calc_create.open"),
    ActionSpec(
        "view.theme",
        MENU_TOOLS,
        _("Alternar tema"),
        "toggle_theme",
        "Ctrl+T",
        separator_before=True,
    ),
    ActionSpec(
        "config.open", MENU_TOOLS, _("Abrir config.yaml"), "open_config", separator_before=True
    ),
    ActionSpec("config.reload", MENU_TOOLS, _("Recarregar config.yaml"), "reload_config"),
    ActionSpec("help.shortcuts", MENU_HELP, _("Atalhos de teclado"), "help.show_shortcuts", "F1"),
    ActionSpec(
        "help.palette", MENU_HELP, _("Paleta de comandos"), "command_palette.open", "Ctrl+K"
    ),
    ActionSpec("help.log", MENU_HELP, _("Abrir log"), "help.open_log"),
    ActionSpec("help.data", MENU_HELP, _("Abrir pasta de dados"), "help.open_data_dir"),
    ActionSpec("help.about", MENU_HELP, _("Sobre o Lain"), "help.show_about"),
)


def build_menus(window: QMainWindow) -> dict[str, QAction]:
    """The menus of ``ACTIONS`` in the window's menu bar, by action id."""
    bar = window.menuBar()
    assert bar is not None
    menus = {}
    actions: dict[str, QAction] = {}
    for spec in ACTIONS:
        if spec.menu not in menus:
            menus[spec.menu] = bar.addMenu(spec.menu)
        menu = menus[spec.menu]
        assert menu is not None
        menu.setToolTipsVisible(True)  # only actions given a tooltip show one (the sync scope)
        if spec.separator_before:
            menu.addSeparator()
        action = menu.addAction(spec.text)
        assert action is not None
        action.setObjectName(spec.id)
        action.triggered.connect(attrgetter(spec.slot)(window))
        if spec.shortcut:
            action.setShortcut(QKeySequence(spec.shortcut))
        actions[spec.id] = action
    return actions
