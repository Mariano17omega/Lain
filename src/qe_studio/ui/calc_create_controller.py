"""The "Criar cálculo" button, action and window (spec 26).

The window gathers the type, the SCF and the fields; the folder is written here, in a worker
(``core/calc_create/writer.create_folder``, which never touches an existing folder and removes what
it wrote when a write fails). Success closes the window, selects the new folder and says so in a
toast; a failure keeps the window open with the reason.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from ..core.calc_create.preview import created_notice
from ..core.calc_create.writer import Created, CreateError, create_folder, preview_name
from ..core.config import JobsConfig
from ..core.tasks import run_task
from .busy import BusyTracker
from .dialogs.calc_create import CalcCreateDialog, CreateRequest
from .theme.manager import ThemeManager
from .widgets.toast import Toast

log = logging.getLogger(__name__)

TITLE = "Criar cálculo"
AVAILABLE_TIP = "Criar cálculo (scripts e inputs)"
MISSING_ROOT_TIP = "Defina paths.local_root para criar cálculos"
BUSY_KEY = "calc:create"


class _Toggle(Protocol):
    """The button and the action: both are enabled and get a tooltip."""

    def setEnabled(self, enabled: bool) -> None: ...  # noqa: N802 (Qt's name)
    def setToolTip(self, tip: str | None) -> None: ...  # noqa: N802


class CalcCreateController(QObject):
    created = pyqtSignal(object)  # Created (tests and scripts wait on it)
    failed = pyqtSignal(str)  # the reason shown

    def __init__(
        self,
        theme: ThemeManager,
        root: Callable[[], Path],
        current_folder: Callable[[], Path],
        jobs: Callable[[], JobsConfig],
        busy: BusyTracker,
        toast: Toast,
        select_path: Callable[[Path], None],
        refresh: Callable[[Path], None],
        targets: Callable[[], Sequence[_Toggle | None]],
        dialog_parent: QWidget,
        parent: QObject | None = None,
        sync_enabled: Callable[[], bool] = lambda: False,
    ):
        super().__init__(parent)
        self._sync_enabled = sync_enabled  # the toast reminds of "Enviar ao cluster" (spec 27)
        self.theme, self._root, self._current_folder, self._jobs = theme, root, current_folder, jobs
        self.busy, self.toast, self._select_path, self._refresh = busy, toast, select_path, refresh
        self._targets, self.dialog_parent = targets, dialog_parent
        self.dialog: CalcCreateDialog | None = None
        self._creating: Path | None = None  # the folder the worker is making a calculation in

    @classmethod
    def for_window(cls, window) -> CalcCreateController:
        """The controller of a ``MainWindow``: its activity bar button, footer spinner and toast."""

        def refresh(folder: Path) -> None:
            window.service.invalidate(folder)
            window.explorer.refresh()
            window.files.refresh()

        controller = cls(
            window.theme,
            root=lambda: window.root,
            current_folder=window.current_folder,
            jobs=lambda: window.config.jobs,
            busy=window.plot_workflow.busy,
            toast=window.toast,
            select_path=window.explorer.select_path,
            refresh=refresh,
            targets=lambda: (window.activity.new_calc, window._actions.get("calc.create")),
            dialog_parent=window,
            parent=window,
            sync_enabled=lambda: window.config.sync_enabled,
        )
        window.activity.create_requested.connect(controller.open)
        window.first_run.refreshed.connect(controller.update_available)  # start and config reload
        return controller

    # -- availability --------------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._root().is_dir()

    def update_available(self) -> None:
        """Without a project folder there is nowhere to start from (spec 18 ``missing_root``)."""
        available = self.available
        for target in self._targets():
            if target is not None:
                target.setEnabled(available)
                target.setToolTip(AVAILABLE_TIP if available else MISSING_ROOT_TIP)

    # -- the window ----------------------------------------------------------------------------
    def open(self) -> None:
        """One window: asking again brings the open one to the front."""
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        if not self.available:
            return
        root = self._root()
        start = self._current_folder()
        dialog = CalcCreateDialog(
            self.theme,
            root,
            start if start.is_dir() else root,
            self._jobs(),
            self.busy,
            self.dialog_parent,
        )
        dialog.create_requested.connect(self.create)
        dialog.finished.connect(self._on_dialog_closed)
        dialog.destroyed.connect(self._on_dialog_closed)
        self.dialog = dialog
        dialog.show()

    def _on_dialog_closed(self, *_args) -> None:
        self.dialog = None

    # -- creating ------------------------------------------------------------------------------
    def creating_under(self, path: Path) -> Path | None:
        """The folder a calculation is being made in, if it lies inside ``path`` (renaming it or
        a folder above it would take the new folder's place from under the worker)."""
        creating = self._creating
        return creating if creating is not None and creating.is_relative_to(path) else None

    def create(self, request: CreateRequest) -> None:
        name = preview_name(request.parent, request.calc_type, request.suffix)
        self._creating = request.parent
        self.busy.begin(BUSY_KEY, f"Criando {name}…")
        if self.dialog is not None:
            self.dialog.set_busy(True)
        run_task(
            create_folder,
            request.parent,
            request.calc_type,
            request.suffix,
            request.plan,
            request.notes,
            on_done=self._on_created,
            on_error=self._on_failed,
        )

    def _on_created(self, created: Created) -> None:
        self._creating = None
        self.busy.end(BUSY_KEY)
        if self.dialog is not None:
            self.dialog.close_created()
        self._refresh(created.folder.parent)
        self._select_path(created.folder)
        text, details = created_notice(created, sync=self._sync_enabled())
        self.toast.show_message(text, "success", details)
        self.created.emit(created)

    def _on_failed(self, exc: BaseException) -> None:
        self._creating = None
        self.busy.end(BUSY_KEY)
        if isinstance(exc, CreateError):
            reason = str(exc)
        else:
            log.error("creating the calculation folder failed", exc_info=exc)
            reason = f"Erro inesperado: {exc}"
        dialog = self.dialog
        if dialog is not None:
            dialog.set_busy(False)
        QMessageBox.critical(dialog or self.dialog_parent, TITLE, reason)
        self.failed.emit(reason)
