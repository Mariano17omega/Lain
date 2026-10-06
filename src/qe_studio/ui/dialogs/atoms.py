"""Pick the atoms a PDOS shows (spec 21): a table of the atoms of the compound with a checkbox each.

Interface only: the atoms come from ``CalculationModule.atoms_of`` and saving is the caller's
(``PlotSession.persist`` writes the compound store), so this window knows no file and no module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.compounds import AtomChoices, normalize_selection
from ..widgets.atom_table import AtomRow, AtomTable
from ..widgets.common import set_variant

NOTHING_MARKED = "Marque ao menos um átomo"
COUNT_FORMAT = "{n} de {m} marcados"


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
        self.setModal(
            True
        )  # no WA_DeleteOnClose: ``exec`` would delete it before the answer is read
        self.resize(560, 480)
        self.sites = sorted(choices.sites, key=lambda site: site.index)

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

        rows = [
            AtomRow(site.index, site.species, f"{site.x:.4f}", f"{site.y:.4f}", f"{site.z:.4f}")
            for site in self.sites
        ]
        self.atoms = AtomTable(rows, selected, "Å", COUNT_FORMAT)
        # What the window's tests and callers reach for, from the table.
        self.table, self.checks, self.count = self.atoms.table, self.atoms.checks, self.atoms.count
        self.mark_all, self.unmark_all = self.atoms.mark_all, self.atoms.unmark_all
        self.invert, self.species_button = self.atoms.invert, self.atoms.species_button
        self.species_menu = self.atoms.species_menu
        layout.addWidget(self.atoms, 1)

        self.problem = set_variant(QLabel(), "warning")
        layout.addWidget(self.problem)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.save_button = set_variant(QPushButton("Salvar"), "primary")
        self.save_button.setDefault(True)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self.atoms.changed.connect(self._clear_problem)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)

    # -- marks ---------------------------------------------------------------------------------
    def checked(self) -> list[int]:
        """The marked atom numbers, ascending."""
        return self.atoms.checked()

    def set_all(self, on: bool) -> None:
        self.atoms.set_all(on)

    def invert_marks(self) -> None:
        self.atoms.invert_marks()

    def only_species(self, species: str) -> None:
        self.atoms.only_species(species)

    def answer(self) -> AtomsAnswer:
        """Every atom marked is None (the default), so the saved file does not hold it."""
        return AtomsAnswer(normalize_selection(self.checked(), list(self.checks)))

    def _clear_problem(self) -> None:
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
    answer = dialog.answer() if accepted else None
    dialog.deleteLater()
    return answer
