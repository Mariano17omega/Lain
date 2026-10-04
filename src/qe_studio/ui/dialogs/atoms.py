"""Pick the atoms a PDOS shows (spec 21): a table of the atoms of the compound with a checkbox each.

Interface only: the atoms come from ``CalculationModule.atoms_of`` and saving is the caller's
(``PlotSession.persist`` writes the compound store), so this window knows no file and no module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.compounds import AtomChoices, normalize_selection
from ..painting import mono_font
from ..widgets.common import set_variant

HEADERS = ("", "#", "Elemento", "x (Å)", "y (Å)", "z (Å)")
NOTHING_MARKED = "Marque ao menos um átomo"


@dataclass(frozen=True)
class AtomsAnswer:
    atoms: list[int] | None  # None = every atom


class AtomsDialog(QDialog):
    def __init__(
        self,
        choices: AtomChoices,
        selected: Sequence[int] | None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Átomos da PDOS")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(560, 480)
        self.sites = sorted(choices.sites, key=lambda site: site.index)
        self.checks: dict[int, QCheckBox] = {}  # by atom number

        layout = QVBoxLayout(self)
        formula = choices.compound.formula if choices.compound else ""
        self.heading = set_variant(QLabel(f"Átomos de {formula}"), "dialogTitle")
        layout.addWidget(self.heading)
        note = QLabel(
            "A seleção vale para todo gráfico deste composto (mesma sequência de espécies), "
            "em qualquer pasta."
        )
        note.setWordWrap(True)
        layout.addWidget(set_variant(note, "dialogText"))

        tools = QHBoxLayout()
        self.mark_all = QPushButton("Marcar todos")
        self.unmark_all = QPushButton("Desmarcar todos")
        self.invert = QPushButton("Inverter")
        self.species_button = QPushButton("Só espécie ▸")
        self.species_menu = QMenu(self.species_button)
        for name in dict.fromkeys(site.species for site in self.sites):
            action = self.species_menu.addAction(name)
            if action is not None:
                action.triggered.connect(lambda _c=False, n=name: self.only_species(n))
        self.species_button.setMenu(self.species_menu)
        for button in (self.mark_all, self.unmark_all, self.invert, self.species_button):
            tools.addWidget(button)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.table = QTableWidget(len(self.sites), len(HEADERS))
        self._build_table(selected)
        layout.addWidget(self.table, 1)

        self.count = set_variant(QLabel(), "dialogText")
        self.problem = set_variant(QLabel(), "warning")
        layout.addWidget(self.count)
        layout.addWidget(self.problem)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.save_button = set_variant(QPushButton("Salvar"), "primary")
        self.save_button.setDefault(True)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self.mark_all.clicked.connect(lambda: self.set_all(True))
        self.unmark_all.clicked.connect(lambda: self.set_all(False))
        self.invert.clicked.connect(self.invert_marks)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        self._update_count()

    # -- table ---------------------------------------------------------------------------------
    def _build_table(self, selected: Sequence[int] | None) -> None:
        table = self.table
        table.setObjectName("atomsTable")
        table.setHorizontalHeaderLabels(list(HEADERS))
        vertical = table.verticalHeader()
        header = table.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        for column in range(len(HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # the element's name
        for column in range(3, len(HEADERS)):  # same width for the three coordinates
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(column, 96)
        chosen = None if selected is None else set(selected)
        for row, site in enumerate(self.sites):
            check = QCheckBox()
            check.setAccessibleName(f"Átomo {site.index} {site.species}")
            check.setChecked(chosen is None or site.index in chosen)
            check.toggled.connect(self._update_count)
            self.checks[site.index] = check
            cell = QWidget()
            box = QHBoxLayout(cell)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(check, 0, Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 0, cell)
            values = (
                str(site.index),
                site.species,
                f"{site.x:.4f}",
                f"{site.y:.4f}",
                f"{site.z:.4f}",
            )
            for column, text in enumerate(values, start=1):
                item = QTableWidgetItem(text)
                item.setFont(mono_font(11))
                align = Qt.AlignmentFlag.AlignVCenter | (
                    Qt.AlignmentFlag.AlignRight if column > 2 else Qt.AlignmentFlag.AlignLeft
                )
                item.setTextAlignment(int(align))
                table.setItem(row, column, item)

    # -- marks ---------------------------------------------------------------------------------
    def checked(self) -> list[int]:
        """The marked atom numbers, ascending."""
        return [index for index, check in sorted(self.checks.items()) if check.isChecked()]

    def set_all(self, on: bool) -> None:
        for check in self.checks.values():
            check.setChecked(on)

    def invert_marks(self) -> None:
        for check in self.checks.values():
            check.setChecked(not check.isChecked())

    def only_species(self, species: str) -> None:
        wanted = {site.index for site in self.sites if site.species == species}
        for index, check in self.checks.items():
            check.setChecked(index in wanted)

    def answer(self) -> AtomsAnswer:
        """Every atom marked is None (the default), so the saved file does not hold it."""
        return AtomsAnswer(normalize_selection(self.checked(), list(self.checks)))

    def _update_count(self) -> None:
        self.count.setText(f"{len(self.checked())} de {len(self.checks)} marcados")
        self.problem.setText("")

    def _save(self) -> None:
        if not self.checked():
            self.problem.setText(NOTHING_MARKED)
            return
        self.accept()


def ask_atoms(
    parent: QWidget, choices: AtomChoices, selected: Sequence[int] | None
) -> AtomsAnswer | None:
    """The new selection, or None when the window was cancelled."""
    dialog = AtomsDialog(choices, selected, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.answer() if accepted else None
