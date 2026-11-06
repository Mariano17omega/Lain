"""The "Visualizar 3D" of "Criar cálculo" (spec 81 R3): one 3D window per dialog that shows what is being
created, made by the dialog's button and closed with it.

The structures are ``core/calc_create/structures.plan_structures``: on step 1 the SCF (or step 1's list of
SCFs), on step 2 also each pw.x input of the plan with a structure of its own, made again whenever the
dialog has a new plan (``refresh``). They are made in a worker, one at a time (a newer source cancels the
older, which never calls back). The window opens on the default one; after that it keeps the one the user
picked in its combo while that label is still listed. A structure the window already shows is not drawn
again, and one with the same cell keeps the camera, so the complex follows distance, Δx, Δy and site
without the view jumping. A source that gives no structure leaves the last one shown, with the reason in
the status bar.

The window is a preview of files that may not exist: no ``view3d.plot`` is read or written (that is only
``Structure3DController``'s) and "Print" works only for a structure with a file.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from ....core.calc_create.scf_info import ScfInfo, same_scfs
from ....core.calc_create.structures import (
    PlanStructure,
    default_index,
    plan_structures,
    same_cell,
    same_view,
)
from ....core.calc_create.types import CalcPlan
from ....core.tasks import TaskGroup
from ....i18n import _
from ...theme.manager import ThemeManager
from ...widgets.structure3d.window import StructureWindow

log = logging.getLogger(__name__)

KEY = "structures"
TITLE = _("Visualizar 3D")
NO_STRUCTURE = _("Nenhuma estrutura para mostrar: o SCF não tem uma estrutura legível")
FAILED = _("Não foi possível montar a estrutura: {error}")

PreviewSource = tuple[ScfInfo, CalcPlan | None, tuple[ScfInfo, ...]]


def warn_failed(parent: QWidget, text: str) -> None:
    """No window to say it in (the first one could not be made); tests replace it."""
    QMessageBox.warning(parent, TITLE, text)


def _same_source(a: PreviewSource | None, b: PreviewSource) -> bool:
    """The same objects: the SCF, the plan and the list (a new plan is a new object)."""
    return a is not None and a[0] is b[0] and a[1] is b[1] and same_scfs(a[2], b[2])


class StructurePreview(QObject):
    opened = pyqtSignal(object)  # the StructureWindow, when it opens
    shown = pyqtSignal()  # a list of structures reached the window (tests wait on it)

    def __init__(
        self,
        theme: ThemeManager,
        settings: QSettings | None,
        parent: QWidget,
        root: Callable[[], Path | None] | None = None,
    ):
        """``settings``: the panel's open sections; ``root``: the project, for the "Print" file name."""
        super().__init__(parent)
        self.theme, self.settings, self._parent, self._root = theme, settings, parent, root
        self.window: StructureWindow | None = None
        self.structures: list[PlanStructure] = []
        self._shown: PlanStructure | None = None
        self._chosen: str | None = None  # the label the user picked in the combo
        self._source: PreviewSource | None = None
        self._wanted = False  # a window is open, or its first structures are being made
        self._tasks = TaskGroup()

    def open(self, scf: ScfInfo, plan: CalcPlan | None, scfs: tuple[ScfInfo, ...]) -> None:
        """The button: the window to the front, or a new one once its structures are made."""
        if self.window is not None:
            self.window.raise_()
            self.window.activateWindow()
        self._wanted = True
        self.refresh(scf, plan, scfs)

    def refresh(self, scf: ScfInfo, plan: CalcPlan | None, scfs: tuple[ScfInfo, ...]) -> None:
        """What the dialog shows now (on every change of it); nothing while no window is wanted."""
        source: PreviewSource = (scf, plan, scfs)
        if not self._wanted or _same_source(self._source, source):
            return
        self._source = source
        self._tasks.submit(
            KEY, plan_structures, scf, plan, scfs, on_done=self._on_built, on_error=self._on_failed
        )

    def _on_built(self, _key: str, structures: list[PlanStructure]) -> None:
        if not structures:
            self._fail(NO_STRUCTURE)
            return
        self.structures = structures
        labels = [each.label for each in structures]
        chosen = self._chosen
        index = labels.index(chosen) if chosen in labels else default_index(structures)
        if self.window is None:
            self._open_window(structures[index])
        else:
            self._show(structures[index])
        assert self.window is not None
        self.window.set_choices(labels, index)
        self.shown.emit()

    def _open_window(self, chosen: PlanStructure) -> None:
        window = StructureWindow(
            chosen.structure, self.theme, self.settings, root=self._root, name=chosen.name
        )
        window.closed.connect(self._on_closed)
        window.choice_changed.connect(self._on_choice)
        self.window, self._shown = window, chosen
        window.show()
        self.opened.emit(window)

    def _show(self, chosen: PlanStructure) -> None:
        """``chosen`` in the window, unless it shows that already."""
        shown, window = self._shown, self.window
        assert window is not None
        if (
            shown is not None
            and shown.name == chosen.name
            and same_view(shown.structure, chosen.structure)
        ):
            self._shown = chosen
            return
        keep = shown is not None and same_cell(shown.structure, chosen.structure)
        window.show_structure(chosen.structure, keep, chosen.name)
        self._shown = chosen

    def _on_choice(self, index: int) -> None:
        if 0 <= index < len(self.structures):
            self._chosen = self.structures[index].label
            self._show(self.structures[index])

    def _on_failed(self, _key: str, exc: BaseException) -> None:
        log.error("task: making the structures of the 3D preview failed", exc_info=exc)
        self._fail(FAILED.format(error=str(exc) or type(exc).__name__))

    def _fail(self, text: str) -> None:
        """The last structure stays in the window; with no window yet, none opens."""
        if self.window is not None:
            self.window.show_notice(text)
            return
        self._wanted, self._source = False, None
        warn_failed(self._parent, text)

    def _on_closed(self, window: StructureWindow) -> None:
        if window is not self.window:
            return
        self._tasks.cancel_all()
        self.window, self._shown, self._chosen, self._source = None, None, None, None
        self.structures, self._wanted = [], False

    def close(self) -> None:
        """The dialog closes: so does the window, and the structures being made are dropped."""
        self._tasks.cancel_all()
        self._wanted = False
        if self.window is not None:
            self.window.close()
