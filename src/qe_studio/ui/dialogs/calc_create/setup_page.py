"""Step 1 of "Criar cálculo" (spec 26 R3, spec 28 R5.3): the type, the SCF input, the folder name
(optional: the folder is then the type's prefix alone) and where it goes.

The SCF is checked on the GUI thread only by its head (``looks_like_input``) and read in a worker
(``read_scf``); the file is never written. The name and the place are checked with ``stat`` only.
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....core.calc_create.preview import OUTSIDE_PROJECT, outside_project, target_text
from ....core.calc_create.scf_info import ScfInfo, ScfInputError, read_scf
from ....core.calc_create.types import REGISTRY, CalcType
from ....core.calc_create.writer import validate_parent, validate_suffix
from ....core.sniff import looks_like_input
from ....core.tasks import TaskGroup
from ...busy import BusyTracker
from ...widgets.common import set_variant
from .labels import message_label, show_message

log = logging.getLogger(__name__)

READING = "Lendo SCF…"
CHOOSE_TYPE = "Escolha o tipo de cálculo"
CHOOSE_SCF = "Escolha o input de SCF"
REBUILD_NOTE = "O tipo ou o SCF mudou: os campos da próxima etapa voltam aos padrões"
INPUT_FILTER = "Inputs do QE (*.in *.pwi *.inp);;Todos os arquivos (*)"


def choose_scf(parent: QWidget, start: Path) -> Path | None:
    path, _filter = QFileDialog.getOpenFileName(
        parent, "Escolher input de SCF", str(start), INPUT_FILTER
    )
    return Path(path) if path else None


def choose_folder(parent: QWidget, start: Path) -> Path | None:
    path = QFileDialog.getExistingDirectory(parent, "Onde criar a pasta", str(start))
    return Path(path) if path else None


class SetupPage(QWidget):
    changed = pyqtSignal()  # anything "Continuar" depends on
    scf_ready = pyqtSignal(object)  # ScfInfo, or None when it could not be used

    def __init__(
        self,
        root: Path,
        start: Path,
        busy: BusyTracker | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.root, self.start, self.busy = root, start, busy
        self._scf: ScfInfo | None = None
        self._scf_path: Path | None = None
        self._scf_problem = ""
        self._reading = False
        self._location = start
        self._tasks = TaskGroup()
        self._busy_key = f"calc:scf:{id(self)}"
        if busy is not None:
            self.destroyed.connect(partial(busy.end, self._busy_key))

        self.type_combo = QComboBox()
        self.type_combo.setAccessibleName("Tipo de cálculo")
        for calc_type in REGISTRY:
            self.type_combo.addItem(calc_type.label, calc_type.id)
        self.type_combo.setPlaceholderText(CHOOSE_TYPE)
        self.type_combo.setCurrentIndex(-1)
        self.type_combo.currentIndexChanged.connect(self._update)
        self.scf_edit = set_variant(QLineEdit(), "mono")
        self.scf_edit.setReadOnly(True)
        self.scf_edit.setPlaceholderText("Nenhum arquivo escolhido")
        self.scf_edit.setAccessibleName("Input de SCF")
        self.scf_button = QPushButton("Escolher…")
        self.scf_button.clicked.connect(self._pick_scf)
        self.scf_message = message_label("error")
        self.suffix_edit = QLineEdit()
        self.suffix_edit.setAccessibleName("Nome da pasta")
        self.suffix_edit.setPlaceholderText("opcional, ex.: Al, Fe_teste")
        self.suffix_edit.textChanged.connect(self._update)
        self.suffix_message = message_label("error")
        self.location_edit = set_variant(QLineEdit(str(start)), "mono")
        self.location_edit.setReadOnly(True)
        self.location_edit.setAccessibleName("Local")
        self.location_button = QPushButton("Escolher…")
        self.location_button.clicked.connect(self._pick_location)
        self.location_message = message_label("warning")
        self.name_preview = set_variant(message_label(), "mono")
        self.rebuild_note = message_label("warning")
        for button in (self.scf_button, self.location_button):
            button.setAutoDefault(False)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(6)
        rows = [
            ("Tipo de cálculo", self.type_combo, None),
            ("Input de SCF *", self._with_button(self.scf_edit, self.scf_button), self.scf_message),
            ("Nome da pasta", self.suffix_edit, self.suffix_message),
            (
                "Local",
                self._with_button(self.location_edit, self.location_button),
                self.location_message,
            ),
        ]
        row = 0
        for label, widget, message in rows:
            grid.addWidget(set_variant(QLabel(label), "fieldLabel"), row, 0)
            grid.addWidget(widget, row, 1)
            row += 1
            if message is not None:
                grid.addWidget(message, row, 1)
                row += 1
        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addSpacing(8)
        layout.addWidget(self.name_preview)
        layout.addWidget(self.rebuild_note)
        layout.addStretch(1)
        self._update()

    @staticmethod
    def _with_button(edit: QLineEdit, button: QPushButton) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return box

    # -- what was chosen -----------------------------------------------------------------------
    @property
    def calc_type(self) -> CalcType | None:
        index = self.type_combo.currentIndex()
        return REGISTRY[index] if 0 <= index < len(REGISTRY) else None

    def set_type(self, type_id: str) -> None:
        self.type_combo.setCurrentIndex(self.type_combo.findData(type_id))

    @property
    def scf(self) -> ScfInfo | None:
        return self._scf

    @property
    def suffix(self) -> str:
        return self.suffix_edit.text().strip()

    @property
    def location(self) -> Path:
        return self._location

    def problems(self) -> list[str]:
        """What keeps "Continuar" disabled, in the order of the rows ([] = nothing)."""
        problems = []
        if self.calc_type is None:
            problems.append(CHOOSE_TYPE)
        if self._scf is None:
            problems.append(self._scf_problem or (READING if self._reading else CHOOSE_SCF))
        return problems + validate_suffix(self.suffix) + validate_parent(self._location)

    def location_warnings(self) -> tuple[str, ...]:
        return (OUTSIDE_PROJECT,) if outside_project(self._location, self.root) else ()

    # -- the SCF -------------------------------------------------------------------------------
    def _pick_scf(self) -> None:
        start = self._scf_path.parent if self._scf_path is not None else self.start
        path = choose_scf(self, start)
        if path is not None:
            self.set_scf(path)

    def set_scf(self, path: Path) -> None:
        """Use ``path`` as the SCF: its head now, its contents in a worker (``scf_ready``)."""
        self._scf, self._scf_path, self._scf_problem = None, path, ""
        self.scf_edit.setText(str(path))
        self._tasks.cancel_all()
        # Accepted, local disk: one file the user just picked, its head only (spec 27-8 R3.3).
        if not path.is_file() or not looks_like_input(path):
            self._scf_problem = f"{path.name} não parece um input do Quantum ESPRESSO"
            self._end_reading()
            self.scf_ready.emit(None)
            return
        self._reading = True
        show_message(self.scf_message, READING, "hint")
        if self.busy is not None:
            self.busy.begin(self._busy_key, READING)
        self._tasks.submit("scf", read_scf, path, on_done=self._on_read, on_error=self._on_failed)
        self._update()

    def _on_read(self, _key: str, info: ScfInfo) -> None:
        self._scf = info
        self._end_reading()
        self.scf_ready.emit(info)

    def _on_failed(self, _key: str, exc: BaseException) -> None:
        if isinstance(exc, ScfInputError):
            self._scf_problem = str(exc)
        else:
            log.error("reading the SCF for a new calculation failed", exc_info=exc)
            self._scf_problem = f"Não foi possível ler o SCF: {exc}"
        self._end_reading()
        self.scf_ready.emit(None)

    def _end_reading(self) -> None:
        self._reading = False
        if self.busy is not None:
            self.busy.end(self._busy_key)
        show_message(self.scf_message, self._scf_problem, "error")
        self._update()

    # -- the place -----------------------------------------------------------------------------
    def _pick_location(self) -> None:
        path = choose_folder(self, self._location)
        if path is not None:
            self.set_location(path)

    def set_location(self, path: Path) -> None:
        self._location = path
        self.location_edit.setText(str(path))
        self._update()

    def show_rebuild_note(self, shown: bool) -> None:
        show_message(self.rebuild_note, REBUILD_NOTE if shown else "")

    def _update(self, *_args) -> None:
        suffix = self.suffix
        named = validate_suffix(suffix)
        show_message(self.suffix_message, named[0] if named else "")
        place = validate_parent(self._location)
        show_message(
            self.location_message,
            "\n".join(place or list(self.location_warnings())),
            "error" if place else "warning",
        )
        calc_type = self.calc_type
        preview = ""
        if calc_type is not None and not named and not place:
            preview = target_text(self._location, calc_type, suffix)
        show_message(self.name_preview, preview)
        self.changed.emit()

    def shutdown(self) -> None:
        self._tasks.shutdown(0)
