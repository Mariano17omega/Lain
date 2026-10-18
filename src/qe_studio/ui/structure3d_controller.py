"""The "Visualização 3D" item of the context menu (spec 43 R4.2): a new window per request, also for
the same file.

The input and its section of ``view3d.plot`` are read in a worker (``core/structure3d/view_file.load_view``:
the GUI never reads them), under the footer spinner "Lendo estrutura…"; then a ``StructureWindow`` opens
with the saved view (spec 47 R2). A file that cannot be shown gives a warning toast and no window. The open
windows are kept here and dropped by their own ``closed`` signal, which is also when their view is saved
(R3): written only when the user changed it, its section removed after "Restaurar padrões", nothing for an
untouched window. Closing the main window closes them all, so they save then too, and its shutdown step
waits for the writes. Only this controller writes ``view3d.plot``, in a queue of its own, one write at a
time and in the order the windows closed (the GUI thread never reads or writes it): with two windows of one
file, the last to close wins.

The second viewer, the external XCrySDen ("Abrir com XCrysDen", spec 45), is launched by ``ItemActions``;
``for_window`` only tells it where the program is (``paths.xcrysden_path``).
"""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QThreadPool, pyqtSignal

from ..core.structure3d.options import DisplayOptions, background_of_theme
from ..core.structure3d.source import StructureReadError
from ..core.structure3d.view_file import LoadedView, load_view, remove_session, write_session
from ..core.structure3d.view_state import apply_options, camera_from_stored
from ..core.tasks import TaskGroup
from ..i18n import _
from .busy import BusyTracker
from .theme.manager import ThemeManager
from .widgets.structure3d.window import StructureWindow
from .widgets.toast import Toast

log = logging.getLogger(__name__)

KEY_PREFIX = "structure3d:"  # of the busy label and the task: ``structure3d:<path>:<n>``
BUSY_LABEL = _("Lendo estrutura…")
SAVE_WAIT_MS = 5000  # ``wait_saves``: a rename waits this long for the views being written


class Structure3DController(QObject):
    opened = pyqtSignal(object)  # StructureWindow (tests and scripts wait on it)
    failed = pyqtSignal(str)  # the message shown
    saved = pyqtSignal(object)  # Path of the file whose view was written or removed

    def __init__(
        self,
        theme: ThemeManager,
        busy: BusyTracker,
        toast: Toast,
        settings: QSettings | None = None,
        parent: QObject | None = None,
        *,
        root: Callable[[], Path | None] | None = None,
    ):
        super().__init__(parent)
        self.theme, self.busy, self.toast, self.settings = theme, busy, toast, settings
        self.root = root  # the project root, read at every "Print" (the file's name, spec 46 R5)
        self.windows: list[StructureWindow] = []
        self._tasks = TaskGroup()
        self._paths: dict[str, Path] = {}
        self._save_pool = QThreadPool()  # no Qt parent: see core/tasks.py, "private pools"
        self._save_pool.setMaxThreadCount(1)  # one at a time: the sections of a folder share a file
        self._saves = TaskGroup(self._save_pool)  # by file: a newer save of it wins
        self._count = itertools.count(1)

    @classmethod
    def for_window(cls, window) -> Structure3DController:
        """The controller of a ``MainWindow``: its context menu, footer spinner, toast and settings."""
        busy = window.plot_workflow.busy
        controller = cls(
            window.theme,
            busy,
            window.toast,
            window.settings,
            window,
            root=lambda: window.config.paths.local_root,
        )
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
            key, load_view, Path(path), on_done=self._on_done, on_error=self._on_error
        )

    def _on_done(self, key: str, loaded: LoadedView) -> None:
        self.busy.end(key)
        self._paths.pop(key, None)
        structure, session = loaded.structure, loaded.session or {}
        for warning in loaded.warnings:  # an unreadable view3d.plot: the defaults
            self.toast.show_message(warning, "warning")
        # a saved background wins over the app theme; without one, the theme as always
        options = DisplayOptions(background=background_of_theme(self.theme.name))
        if "options" in session:
            ignored = apply_options(options, session["options"], structure)
            if ignored:
                log.warning("view3d.plot of %s: ignored %s", structure.source.path, ignored)
        camera = camera_from_stored(session.get("camera"))
        if "camera" in session and camera is None:
            log.warning("view3d.plot of %s: camera ignored", structure.source.path)
        window = StructureWindow(
            structure, self.theme, self.settings, options=options, camera=camera, root=self.root
        )
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
            reason = _("Erro inesperado: {error}").format(error=exc)
        message = _("Visualização 3D de {name}: {reason}").format(name=path.name, reason=reason)
        self.toast.show_message(message, "warning")
        self.failed.emit(message)

    def _on_closed(self, window: StructureWindow) -> None:
        if window in self.windows:
            self.windows.remove(window)
        self._save(window)

    def _save(self, window: StructureWindow) -> None:
        """Spec 47 R3: the view of a window that closes. Changed (also after a restore) → its section is
        written; restored and left alone → its section goes; untouched → the file is not touched. The
        view is taken here; the file is read and written in the save queue."""
        source = window.structure.source.path
        if not source:
            return
        path, canvas = Path(source), window.canvas
        if canvas.dirty:
            job, args = write_session, (path.parent, path.name, window.view_session())
        elif canvas.restored:
            job, args = remove_session, (path.parent, path.name)
        else:
            return
        self._saves.submit(str(path), job, *args, on_done=self._on_saved)

    def _on_saved(self, key: str, warning: str | None) -> None:
        if warning:
            log.warning("%s", warning)
            self.toast.show_message(warning, "warning")
        self.saved.emit(Path(key))

    @property
    def saving(self) -> bool:
        """A view is still being written (or its result not delivered yet)."""
        return len(self._saves) > 0

    def wait_saves(self, timeout_ms: int = SAVE_WAIT_MS) -> bool:
        """Block until the queued views are written (before a rename moves their folder); False on
        timeout."""
        return self._saves.wait(timeout_ms)

    def shutdown(self, timeout_ms: int) -> bool:
        """Window close, after ``close_dialog``: the views of the windows just closed are written within
        ``timeout_ms``; what is still queued then is dropped (a slow disk must not hold the exit)."""
        deadline = time.monotonic() + timeout_ms / 1000
        drained = self._saves.wait(timeout_ms)
        left = max(0, int((deadline - time.monotonic()) * 1000))
        return self._saves.shutdown(left) and drained

    def close_dialog(self) -> bool:
        """The main window is closing: every 3D window closes (and saves its view: ``_on_closed``)."""
        for window in list(self.windows):
            window.close()
        return True

    def cancel(self) -> None:
        """Window close: the readings not finished are dropped."""
        for key in list(self._paths):
            self.busy.end(key)
        self._paths.clear()
        self._tasks.cancel_all()
