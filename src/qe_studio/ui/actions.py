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


class ActionSpec(NamedTuple):
    id: str
    menu: str
    text: str
    slot: str
    shortcut: str | None = None
    separator_before: bool = False


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("files.refresh", "Arquivo", "Atualizar", "refresh", "F5"),
    ActionSpec(
        "files.open_external",
        "Arquivo",
        "Abrir pasta no gerenciador de arquivos",
        "open_folder_externally",
    ),
    ActionSpec("tabs.close", "Arquivo", "Fechar aba", "workspace.close_current", "Ctrl+W"),
    ActionSpec("app.quit", "Arquivo", "Sair", "close", "Ctrl+Q", separator_before=True),
    ActionSpec("nav.back", "Navegar", "Voltar", "navigation.back", "Alt+Left"),
    ActionSpec("nav.forward", "Navegar", "Avançar", "navigation.forward", "Alt+Right"),
    ActionSpec("sync.start", "Cluster", "Sincronizar pasta selecionada", "start_sync"),
    ActionSpec("sync.test", "Cluster", "Testar conexão", "sync.check_connection"),
    ActionSpec("plot.generate", "Gráficos", "Gerar gráfico", "generate_plot", "Ctrl+G"),
    ActionSpec("plot.export", "Gráficos", "Exportar gráfico", "export_plot", "Ctrl+E"),
    ActionSpec("view.theme", "Ferramentas", "Alternar tema", "toggle_theme", "Ctrl+T"),
    ActionSpec(
        "config.open", "Ferramentas", "Abrir config.yaml", "open_config", separator_before=True
    ),
    ActionSpec("config.reload", "Ferramentas", "Recarregar config.yaml", "reload_config"),
    ActionSpec("help.shortcuts", "Ajuda", "Atalhos de teclado", "help.show_shortcuts", "F1"),
    ActionSpec("help.palette", "Ajuda", "Paleta de comandos", "command_palette.open", "Ctrl+K"),
    ActionSpec("help.log", "Ajuda", "Abrir log", "help.open_log"),
    ActionSpec("help.data", "Ajuda", "Abrir pasta de dados", "help.open_data_dir"),
    ActionSpec("help.about", "Ajuda", "Sobre o Lain", "help.show_about"),
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
