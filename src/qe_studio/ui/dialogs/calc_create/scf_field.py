"""A field of "Criar cálculo" that picks another SCF input (spec 40 R1.3): the molecule of a surface.

The file is chosen with step 1's dialog (``setup_page.choose_scf``, called through its module so tests
replace it) and read in a worker (``read_other_scf``: its head is checked there too, so nothing touches
the disk on the GUI thread). While it reads, the line under the field says so; a file that cannot be
used leaves the field empty with the reason in red. ``changed`` fires when a reading ends and when the
field is cleared. The window ends the reading with ``shutdown``, never from ``destroyed``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ....core.calc_create.scf_info import ScfInfo, ScfInputError, read_other_scf
from ....core.tasks import TaskGroup
from ...widgets.common import set_variant
from . import setup_page
from .labels import message_label, show_message

log = logging.getLogger(__name__)

READING = "Lendo SCF…"
EMPTY = "Nenhum arquivo escolhido"


class ScfFileField(QWidget):
    changed = pyqtSignal()  # a reading ended or the field was cleared

    def __init__(
        self,
        start: Path,
        optional: bool = True,
        label: str = "",
        hint: str = "",
        parent: QWidget | None = None,
    ):
        """``start``: where the file dialog opens first; ``hint``: a line under the field."""
        super().__init__(parent)
        self.start = start
        self._value: ScfInfo | None = None
        self._path: Path | None = None
        self._tasks = TaskGroup()
        self.edit = set_variant(QLineEdit(), "mono")
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText(EMPTY)
        self.edit.setAccessibleName(label)
        self.choose_button = QPushButton("Escolher…")
        self.choose_button.clicked.connect(self._pick)
        self.clear_button = QPushButton("Limpar")
        self.clear_button.clicked.connect(self.clear)
        self.clear_button.setVisible(optional)
        self.clear_button.setEnabled(False)
        for button in (self.choose_button, self.clear_button):
            button.setAutoDefault(False)
        self.message = message_label("error")
        self.hint = message_label()
        show_message(self.hint, hint)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(self.choose_button)
        row.addWidget(self.clear_button)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        column.addLayout(row)
        column.addWidget(self.message)
        column.addWidget(self.hint)

    def value(self) -> ScfInfo | None:
        return self._value

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def reading(self) -> bool:
        return self._tasks.active("scf") is not None

    def _pick(self) -> None:
        start = self._path.parent if self._path is not None else self.start
        path = setup_page.choose_scf(self, start)
        if path is not None:
            self.set_path(path)

    def set_path(self, path: Path) -> None:
        """Read ``path`` in a worker; the field holds no SCF until it ends."""
        self._value, self._path = None, path
        self.edit.setText(str(path))
        self.clear_button.setEnabled(True)
        show_message(self.message, READING, "hint")
        self._tasks.submit(
            "scf", read_other_scf, path, on_done=self._on_read, on_error=self._on_failed
        )

    def _on_read(self, _key: str, info: ScfInfo) -> None:
        self._value = info
        show_message(self.message, "")
        self.changed.emit()

    def _on_failed(self, _key: str, exc: BaseException) -> None:
        if isinstance(exc, ScfInputError):
            text = str(exc)
        else:
            log.error("reading a second SCF for a new calculation failed", exc_info=exc)
            text = f"Não foi possível ler o SCF: {exc}"
        self._value = None
        show_message(self.message, text, "error")
        self.changed.emit()

    def clear(self) -> None:
        self._tasks.cancel_all()
        self._value, self._path = None, None
        self.edit.clear()
        self.clear_button.setEnabled(False)
        show_message(self.message, "")
        self.changed.emit()

    def shutdown(self) -> None:
        """The window is done: a file still being read is dropped."""
        self._tasks.shutdown(0)
