"""First run and missing project folder (spec 18 R5): an empty state over the tree and the grid.

Two situations, told apart by the loaded config:

- no ``config.yaml`` was found (``LoadedConfig.first_run``): offer to *create* one from the
  packaged template, optionally with the chosen folder as ``paths.local_root``;
- the config exists but ``paths.local_root`` does not: offer to open it, or to browse a folder for
  this session only. An existing config is never rewritten (PRD §6: it belongs to the user).

The overlay is a child of the splitter's parent, kept on top of the splitter by an event filter,
so the layout controller (which looks at the splitter) never knows it is there.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, pyqtSignal
from PyQt6.QtWidgets import QSplitter, QWidget

from ..core.config import LoadedConfig, user_config_path
from ..core.config_template import create_config
from .dialogs.first_run import ask_create_config, ask_create_with_folder, choose_folder
from .widgets.empty_state import EmptyState

log = logging.getLogger(__name__)

TEMPORARY = "Pasta temporária: para fixar, edite paths.local_root no config.yaml"
AFTER_EDIT = "Depois de editar, use Ferramentas ▸ Recarregar config.yaml"


class FirstRunController(QObject):
    message = pyqtSignal(str, str, int)  # text, level, timeout ms

    def __init__(
        self,
        window: QWidget,
        splitter: QSplitter,
        loaded: Callable[[], LoadedConfig],
        open_in_app: Callable[[Path], None],
        open_external: Callable[[Path], None],
        load_config_file: Callable[[Path], None],
        use_session_root: Callable[[Path], None],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.window, self._splitter, self._loaded = window, splitter, loaded
        self._open_in_app, self._open_external = open_in_app, open_external
        self._load_config_file, self._use_session_root = load_config_file, use_session_root
        host = splitter.parentWidget() or window
        self.overlay = EmptyState(host)
        self.overlay.hide()
        splitter.installEventFilter(self)

    @classmethod
    def for_window(cls, window) -> FirstRunController:
        """The controller of a ``MainWindow``: it covers the window's splitter."""
        return cls(
            window,
            window.splitter,
            lambda: window.loaded,
            window.open_file,
            window.item_actions.open_default,
            window.load_config_file,
            window.use_session_root,
            parent=window,
        )

    # -- state ----------------------------------------------------------------------------
    @property
    def state(self) -> str | None:
        """``"first_run"``, ``"missing_root"`` or None (nothing to show)."""
        loaded = self._loaded()
        if loaded.first_run:
            return "first_run"
        return None if loaded.config.paths.local_root.is_dir() else "missing_root"

    def refresh(self) -> None:
        """Show the empty state that fits the loaded config, or hide it."""
        state = self.state
        if state == "first_run":
            self.overlay.set_content(
                "Bem-vindo ao Lain",
                "Nenhum config.yaml encontrado. O Lain usa um arquivo de configuração "
                "(não há janela de configurações).",
                [
                    ("Criar config…", "primary", self.create_config),
                    ("Escolher pasta…", "", self.choose_project_folder),
                ],
            )
        elif state == "missing_root":
            root = self._loaded().config.paths.local_root
            self.overlay.set_content(
                "Pasta do projeto não encontrada",
                f"A pasta do projeto não foi encontrada: {root}",
                [
                    ("Abrir config", "primary", self.open_config),
                    ("Escolher pasta…", "", self.choose_session_folder),
                ],
            )
        self.overlay.setVisible(state is not None)
        self._place()

    def _place(self) -> None:
        self.overlay.setGeometry(self._splitter.geometry())
        self.overlay.raise_()

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        moved = (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show)
        placed = obj is self._splitter and event is not None and event.type() in moved
        if (
            placed and not self.overlay.isHidden()
        ):  # not isVisible(): the window may not be shown yet
            self._place()
        return False

    # -- actions --------------------------------------------------------------------------
    def create_config(self) -> None:
        """ "Criar config…": the template at the user config path, opened for editing."""
        path = user_config_path()
        if not path.exists():
            if not ask_create_config(self.window, path):
                return
            try:
                create_config(path)
            except OSError as exc:
                log.warning("could not create %s: %s", path, exc)
                self.message.emit(
                    f"Não foi possível criar {path}: {exc.strerror or exc}", "error", 0
                )
                return
        self._edit(path)
        self.message.emit(AFTER_EDIT, "info", 0)

    def choose_project_folder(self) -> None:
        """First run, "Escolher pasta…": a new config whose project is the chosen folder."""
        folder = choose_folder(self.window)
        if folder is None:
            return
        path = user_config_path()
        if path.exists():  # created meanwhile: do not touch it, just use it
            self._load_config_file(path)
            return
        if not ask_create_with_folder(self.window, folder):
            return
        try:
            create_config(path, local_root=folder)
        except OSError as exc:
            log.warning("could not create %s: %s", path, exc)
            self.message.emit(f"Não foi possível criar {path}: {exc.strerror or exc}", "error", 0)
            return
        self._load_config_file(path)

    def open_config(self) -> None:
        """Missing project folder, "Abrir config": the config in the viewer and the editor."""
        path = self._loaded().path
        if path is None:
            self.create_config()
        else:
            self._edit(path)

    def choose_session_folder(self) -> None:
        """Missing project folder, "Escolher pasta…": this session only; the config is untouched."""
        folder = choose_folder(self.window)
        if folder is None:
            return
        self._use_session_root(folder)
        self.message.emit(TEMPORARY, "warning", 0)

    def _edit(self, path: Path) -> None:
        self._open_in_app(path)
        self._open_external(path)
