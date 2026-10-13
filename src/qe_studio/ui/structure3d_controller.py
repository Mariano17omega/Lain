"""The "Visualização 3D" item of the context menu (spec 43 R4.2): a new window per request, also for
the same file.

The input is read in a worker (``core/structure3d/source.read_structure``: the GUI never reads it), under
the footer spinner "Lendo estrutura…"; then a ``StructureWindow`` opens. A file that cannot be shown gives
a warning toast and no window. The open windows are kept here and dropped by their own ``closed`` signal;
closing the main window closes them all (they have nothing to save).

The second viewer, the external XCrySDen ("Abrir com XCrysDen", spec 45), is launched by ``ItemActions``;
``for_window`` only tells it where the program is (``paths.xcrysden_path``).
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

from ..core.structure3d.model import Structure
from ..core.structure3d.source import StructureReadError, read_structure
from ..core.tasks import TaskGroup
from .busy import BusyTracker
from .theme.manager import ThemeManager
from .widgets.structure3d.window import StructureWindow
from .widgets.toast import Toast

log = logging.getLogger(__name__)

KEY_PREFIX = "structure3d:"  # of the busy label and the task: ``structure3d:<path>:<n>``
BUSY_LABEL = "Lendo estrutura…"


class Structure3DController(QObject):
    opened = pyqtSignal(object)  # StructureWindow (tests and scripts wait on it)
    failed = pyqtSignal(str)  # the message shown

    def __init__(
        self,
        theme: ThemeManager,
        busy: BusyTracker,
        toast: Toast,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.theme, self.busy, self.toast, self.settings = theme, busy, toast, settings
        self.windows: list[StructureWindow] = []
        self._tasks = TaskGroup()
        self._paths: dict[str, Path] = {}
        self._count = itertools.count(1)

    @classmethod
    def for_window(cls, window) -> Structure3DController:
        """The controller of a ``MainWindow``: its context menu, footer spinner, toast and settings."""
        busy = window.plot_workflow.busy
        controller = cls(window.theme, busy, window.toast, window.settings, window)
        window.item_actions.structure_requested.connect(controller.open)
        # Read at every menu, so "Recarregar config.yaml" applies without a restart (spec 45).
        window.item_actions.xcrysden_path = lambda: window.config.paths.xcrysden_path
        return controller

    def open(self, path: Path) -> None:
        """Read ``path`` and open a new window on it (every request opens one)."""
        key = f"{KEY_PREFIX}{path}:{next(self._count)}"
        self._paths[key] = Path(path)
        self.busy.begin(key, BUSY_LABEL)
        self._tasks.submit(
            key, read_structure, Path(path), on_done=self._on_done, on_error=self._on_error
        )

    def _on_done(self, key: str, structure: Structure) -> None:
        self.busy.end(key)
        self._paths.pop(key, None)
        window = StructureWindow(structure, self.theme, self.settings)
        window.closed.connect(self._on_closed)
        self.windows.append(window)
        window.show()
        self.opened.emit(window)

    def _on_error(self, key: str, exc: BaseException) -> None:
        self.busy.end(key)
        path = self._paths.pop(key, Path(key.removeprefix(KEY_PREFIX)))
        if isinstance(exc, StructureReadError):
            reason = str(exc)
        else:
            log.error("reading the structure of %s failed", path, exc_info=exc)
            reason = f"Erro inesperado: {exc}"
        message = f"Visualização 3D de {path.name}: {reason}"
        self.toast.show_message(message, "warning")
        self.failed.emit(message)

    def _on_closed(self, window: StructureWindow) -> None:
        if window in self.windows:
            self.windows.remove(window)

    def close_dialog(self) -> bool:
        """The main window is closing: every 3D window closes (nothing to protect)."""
        for window in list(self.windows):
            window.close()
        return True

    def cancel(self) -> None:
        """Window close: the readings not finished are dropped."""
        for key in list(self._paths):
            self.busy.end(key)
        self._paths.clear()
        self._tasks.cancel_all()
