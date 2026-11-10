"""The list of SCF inputs of step 1 for a type that runs several (spec 79 R1): "Energia de adsorção".

"Adicionar…" picks several files at once (and can be clicked again for another folder), "Remover" drops
the selected rows. Each file is read in a worker (``read_other_scf``: its head is checked there too, so
nothing touches the disk on the GUI thread); its row says "lendo…", the error, or the ``prefix`` and the
number of atoms. A file already in the list is refused. ``changed`` fires when the list or a reading
changes. The window ends the readings with ``shutdown``, never from ``destroyed``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....core.calc_create.scf_info import ScfInfo, ScfInputError, read_other_scf
from ....core.tasks import TaskGroup
from ....i18n import _
from ...shell.busy import BusyTracker
from ...widgets.common import set_variant
from .labels import READING, message_label, show_message

log = logging.getLogger(__name__)

INPUT_FILTER = _("Inputs do QE (*.in *.pwi *.inp);;Todos os arquivos (*)")
MINIMUM = 2
TOO_FEW = _("Escolha pelo menos dois inputs de SCF")


def choose_scfs(parent: QWidget, start: Path) -> list[Path]:
    paths, _filter = QFileDialog.getOpenFileNames(
        parent, _("Escolher inputs de SCF"), str(start), INPUT_FILTER
    )
    return [Path(path) for path in paths]


@dataclass
class _Entry:
    path: Path
    info: ScfInfo | None = None
    error: str = ""

    @property
    def text(self) -> str:
        if self.error:
            return f"{self.path}: {self.error}"
        if self.info is None:
            return _("{path}: lendo…").format(path=self.path)
        atoms = self.info.nat if self.info.nat is not None else "?"
        return _("{path} · prefix {prefix}, {atoms} átomos").format(
            path=self.path, prefix=self.info.prefix, atoms=atoms
        )


class ScfList(QWidget):
    changed = pyqtSignal()  # a file was added or removed, or a reading ended

    def __init__(
        self,
        start: Path,
        label: str = "",
        busy: BusyTracker | None = None,
        parent: QWidget | None = None,
    ):
        """``start``: where the file dialog opens first; ``busy``: the window's spinner."""
        super().__init__(parent)
        self.start, self.busy = start, busy
        self._entries: list[_Entry] = []
        self._tasks = TaskGroup()
        self._busy_key = f"calc:scfs:{id(self)}"
        self.list = set_variant(QListWidget(), "mono")
        self.list.setObjectName("scfList")
        self.list.setAccessibleName(label)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._show_buttons)
        self.add_button = QPushButton(_("Adicionar…"))
        self.add_button.clicked.connect(self._pick)
        self.remove_button = QPushButton(_("Remover"))
        self.remove_button.clicked.connect(self.remove_selected)
        for button in (self.add_button, self.remove_button):
            button.setAutoDefault(False)
        self.message = message_label("error")

        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.list, 1)
        row.addLayout(buttons)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        column.addLayout(row)
        column.addWidget(self.message)
        self._show_buttons()

    # -- what it holds ---------------------------------------------------------------------------
    @property
    def scfs(self) -> tuple[ScfInfo, ...]:
        """The SCFs read, in the list's order."""
        return tuple(entry.info for entry in self._entries if entry.info is not None)

    @property
    def paths(self) -> list[Path]:
        return [entry.path for entry in self._entries]

    @property
    def reading(self) -> bool:
        return len(self._tasks) > 0

    def problem(self) -> str:
        """Why the list cannot go on ("" = it can): a file that failed, a reading, too few."""
        failed = next((entry for entry in self._entries if entry.error), None)
        if failed is not None:
            return f"{failed.path.name}: {failed.error}"
        if self.reading:
            return READING
        return TOO_FEW if len(self._entries) < MINIMUM else ""

    # -- adding and removing ---------------------------------------------------------------------
    def _pick(self) -> None:
        start = self._entries[-1].path.parent if self._entries else self.start
        paths = choose_scfs(self, start)
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths: list[Path]) -> None:
        """Read each new path in a worker; one already in the list is refused (and said)."""
        known = set(self.paths)
        repeated = []
        for path in paths:
            if path in known:
                repeated.append(path.name)
                continue
            known.add(path)
            entry = _Entry(path)
            self._entries.append(entry)
            self.list.addItem(entry.text)
            self._tasks.submit(
                path, read_other_scf, path, on_done=self._on_read, on_error=self._on_failed
            )
        show_message(
            self.message,
            "\n".join(_("{name} já está na lista").format(name=name) for name in repeated),
        )
        if self.busy is not None and self.reading:
            self.busy.begin(self._busy_key, READING)
        self.changed.emit()

    def remove_selected(self) -> None:
        rows = sorted((index.row() for index in self.list.selectedIndexes()), reverse=True)
        for row in rows:
            entry = self._entries.pop(row)
            self._tasks.cancel(entry.path)
            self.list.takeItem(row)
        show_message(self.message, "")
        self._end_reading()
        self.changed.emit()

    # -- readings --------------------------------------------------------------------------------
    def _entry(self, path: Path) -> tuple[int, _Entry] | None:
        return next(
            ((row, entry) for row, entry in enumerate(self._entries) if entry.path == path), None
        )

    def _on_read(self, path: Path, info: ScfInfo) -> None:
        self._finish(path, info, "")

    def _on_failed(self, path: Path, exc: BaseException) -> None:
        if isinstance(exc, ScfInputError):
            text = str(exc)
        else:
            log.error("file: reading an SCF of the list for a new calculation failed", exc_info=exc)
            text = _("Não foi possível ler o SCF: {error}").format(error=exc)
        self._finish(path, None, text)

    def _finish(self, path: Path, info: ScfInfo | None, error: str) -> None:
        found = self._entry(path)
        if found is not None:
            row, entry = found
            entry.info, entry.error = info, error
            item = self.list.item(row)
            if item is not None:
                item.setText(entry.text)
        self._end_reading()
        self.changed.emit()

    def _end_reading(self) -> None:
        if self.busy is not None and not self.reading:
            self.busy.end(self._busy_key)

    def _show_buttons(self) -> None:
        self.remove_button.setEnabled(bool(self.list.selectedIndexes()))

    def shutdown(self) -> None:
        """The window is done: the files still being read are dropped, and so is the spinner."""
        self._tasks.shutdown(0)
        if self.busy is not None:
            self.busy.end(self._busy_key)
