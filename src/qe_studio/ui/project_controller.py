"""Projects (spec 31): the "Projeto" dropdown and what it narrows.

A project is a first-level folder of ``paths.local_root`` (``core/projects``). With one selected the
window behaves as if its root were that folder: the tree, the grid's ``..``, the breadcrumb, the
favorite / recent sections, the palette's folder rows, the scope of "Sincronizar projeto" and the
default place of "Criar cálculo". The data (``FolderMemory``, ``NavigationStore``, ``GridStore``…)
stays keyed by ``local_root``. "Todos os projetos" is the root, as before the dropdown.

The widgets get small calls (``set_scope`` and the like) and know nothing of "projeto". The one
entrance to everything is ``ExplorerPanel.select_path``: a path outside the tree's root (history,
"Revelar no explorador", a folder made elsewhere…) raises ``outside_scope`` and the window changes
project to the path's before it is selected. Nothing here reads the disk on the GUI thread: the
list of projects and the creation of one run in workers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from .. import APP_NAME, __version__
from ..core import cancel
from ..core.fuzzy import fold
from ..core.projects import ProjectError, create_project, list_projects, project_of
from ..core.tasks import TaskGroup, run_task
from .busy import BusyTracker
from .dialogs.new_project import ask_new_project
from .navigation_controller import NavigationController
from .sync_coordinator import SyncCoordinator
from .widgets.explorer import ExplorerPanel
from .widgets.file_grid import FilePanel
from .widgets.toast import Toast

log = logging.getLogger(__name__)

SETTING = "explorer/project"  # the project's name; empty = "Todos os projetos"
BUSY_KEY = "project:create"
LIST_KEY = "projects:list"
TITLE = "Criar projeto"


class ProjectController(QObject):
    project_changed = pyqtSignal(object)  # the selected project's folder, None for "Todos"
    listed = pyqtSignal(list)  # the names, after every list (tests wait on it)
    created = pyqtSignal(object)  # Path of the new project's folder
    failed = pyqtSignal(str)  # why a project was not created
    message = pyqtSignal(str, str, int)  # footer text, level, timeout (ms)

    def __init__(
        self,
        explorer: ExplorerPanel,
        files: FilePanel,
        navigation: NavigationController,
        sync: SyncCoordinator,
        busy: BusyTracker,
        toast: Toast,
        settings: QSettings,
        root: Callable[[], Path],
        hidden_dirs: Callable[[], list[str]],
        set_title: Callable[[str], None],
        available: Callable[[], bool],
        dialog_parent: QWidget,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.explorer, self.files, self.navigation, self.sync = explorer, files, navigation, sync
        self.busy, self.toast, self.settings = busy, toast, settings
        self._root, self._hidden, self._set_title = root, hidden_dirs, set_title
        self._available, self._dialog_parent = available, dialog_parent
        self.combo = explorer.projects
        self.project: str | None = None  # the selected project's name; None = "Todos os projetos"
        self._names: list[str] = []  # the last list
        self._expected: str | None = None  # the name restored, checked against the first list
        self._tasks = TaskGroup()
        self._creating = False

    @classmethod
    def for_window(cls, window) -> ProjectController:
        """The controller of a ``MainWindow``: its explorer, grid, navigation and sync. It applies
        the project stored last time at once (no disk read: the first list checks it)."""
        controller = cls(
            window.explorer,
            window.files,
            window.navigation,
            window.sync,
            window.plot_workflow.busy,
            window.toast,
            window.settings,
            root=lambda: window.root,
            hidden_dirs=lambda: window.config.ui.hidden_dirs,
            set_title=window.setWindowTitle,
            available=lambda: window.first_run.state is None,
            dialog_parent=window,
            parent=window,
        )
        explorer = window.explorer
        explorer.projects.project_chosen.connect(controller.on_chosen)
        explorer.projects.create_requested.connect(controller.open_new)
        explorer.outside_scope.connect(controller.on_outside_scope)
        window.first_run.refreshed.connect(controller.update_available)
        controller.message.connect(window.status.set_message)
        controller.start()
        return controller

    # -- the scope -----------------------------------------------------------------------------
    @property
    def view_root(self) -> Path:
        """The folder the window shows as its top: the project's, else the root."""
        root = self._root()
        return root / self.project if self.project else root

    @property
    def names(self) -> list[str]:
        return list(self._names)

    def start(self) -> None:
        """Window start: the project of last time, its list on the way."""
        stored = self.settings.value(SETTING, "", type=str)
        self.project = stored or None
        self._expected = self.project
        self._apply()
        self.update_available()
        self.reload()

    def switch(self, name: str | None, *, select: bool = True) -> None:
        """Show project ``name`` (``None``: all), and by default select its folder like a click on
        the tree would (history, grid, sync scope)."""
        self.project = name
        self.settings.setValue(SETTING, name or "")
        self._apply()
        if select:
            self.explorer.select_path(self.view_root)

    def _apply(self) -> None:
        top = self.view_root
        self.explorer.set_scope(top)
        self.files.set_view_root(top)
        self.navigation.set_view_root(top)
        self.sync.set_project(top if self.project else None)
        self.combo.set_current(self.project)
        where = f"Projeto: {self.project}" if self.project else f"Raiz: {self._root()}"
        self._set_title(f"{APP_NAME} v{__version__} — [{where}]")
        self.project_changed.emit(top if self.project else None)

    def config_applied(self, old_root: Path) -> None:
        """After a config reload (the views were reset to the root): the same root keeps its
        project, another root starts on "Todos"."""
        if self._root() != old_root:
            self.project = None
            self.settings.setValue(SETTING, "")
        self._expected = self.project
        self._apply()
        if self.project:
            self.explorer.select_path(self.view_root)  # the grid was sent to the root
        self.update_available()  # the window's ``refresh`` that follows reads the list again

    def on_chosen(self, name: object) -> None:
        """The user picked "Todos" (``None``) or a project in the dropdown."""
        self.switch(name if isinstance(name, str) else None)

    def on_outside_scope(self, path: Path) -> None:
        """``select_path`` was asked for a folder above the tree's root: show the project that
        holds it, then select it. A path outside the root is not ours to show."""
        root = self._root()
        if not path.is_relative_to(root):
            return
        self.switch(project_of(path, root), select=False)
        if path.is_relative_to(self.explorer.root):  # in scope now: no loop if it is not
            self.explorer.select_path(path)

    def update_available(self) -> None:
        """Without a root folder (spec 18 ``missing_root``) there is nothing to choose from."""
        self.combo.setEnabled(self._available())

    # -- the list ------------------------------------------------------------------------------
    def reload(self) -> None:
        """Read the projects again (start, F5, another root, a rename or a new project). The
        dropdown keeps the last list while it runs."""
        self._tasks.submit(
            LIST_KEY,
            list_projects,
            self._root(),
            list(self._hidden()),
            cancelled=cancel.is_cancelled,
            on_done=self._on_listed,
            on_error=self._on_list_failed,
        )

    def _on_listed(self, _key: str, projects: list) -> None:
        self._apply_names([project.name for project in projects])

    def _on_list_failed(self, _key: str, exc: Exception) -> None:
        log.error("listing the projects failed", exc_info=exc)

    def _apply_names(self, names: list[str]) -> None:
        self._names = names
        self.combo.set_projects(names)
        expected, self._expected = self._expected, None  # only the first list checks the restore
        gone = [name for name in (expected, self.project) if name and name not in names]
        if gone:
            self.message.emit(f"Projeto {gone[0]} não encontrado", "warning", 6000)
            if self.project in gone:
                self.switch(None)
        self.listed.emit(names)

    # -- "Criar projeto…" ----------------------------------------------------------------------
    def open_new(self) -> None:
        """Ask for a name and make the folder (the dropdown's last item, "Arquivo", the palette)."""
        if self._creating:
            return
        name = ask_new_project(self._dialog_parent, self._names, list(self._hidden()))
        if name is None:
            self.combo.restore()  # the dropdown goes back to the project it was on
            return
        self._creating = True
        self.busy.begin(BUSY_KEY, "Criando projeto…")
        run_task(
            create_project,
            self._root(),
            name,
            list(self._hidden()),
            on_done=self._on_created,
            on_error=self._on_failed,
        )

    def _on_created(self, path: Path) -> None:
        self._creating = False
        self.busy.end(BUSY_KEY)
        names = sorted({*self._names, path.name}, key=lambda name: (fold(name), name))
        self._names = names
        self.combo.set_projects(names)
        self.switch(path.name)
        self.toast.show_message(f"Projeto {path.name} criado", "success")
        self.reload()
        self.created.emit(path)

    def _on_failed(self, exc: BaseException) -> None:
        self._creating = False
        self.busy.end(BUSY_KEY)
        self.combo.restore()
        if isinstance(exc, ProjectError):
            reason = str(exc)
        else:
            log.error("creating the project failed", exc_info=exc)
            reason = f"Erro inesperado: {exc}"
        QMessageBox.warning(self._dialog_parent, TITLE, reason)
        self.failed.emit(reason)

    # -- window close --------------------------------------------------------------------------
    def cancel(self) -> None:
        """Window close: the list in progress is dropped."""
        self._tasks.cancel_all()
