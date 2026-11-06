"""The "Energia de adsorção" window (spec 78 R3.3): the energies of the selected SCF outputs and an
equation over them, recomputed at every edit.

Not modal: several can stay open. It never reads a file: the rows come from the controller's worker,
and "Salvar resultado" asks the controller to write the report.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.analysis.adsorption_energy import (
    EnergyRow,
    Outcome,
    calculate,
    default_equation,
    role_label,
)
from ...i18n import _
from ..theme.manager import ThemeManager
from ..widgets.common import set_variant
from ..widgets.painting import mono_font

TITLE = _("Energia de adsorção")
HEADERS = (_("Papel"), _("Prefixo"), _("Arquivo"), _("Átomos"), _("Energia total (Ry)"))
VARIABLE = "variable"  # the property of a variable's button: the text it inserts


class AdsorptionEnergyDialog(QDialog):
    save_requested = pyqtSignal(object, str)  # this dialog, the equation
    closed = pyqtSignal(object)  # this dialog

    def __init__(
        self, rows: Sequence[EnergyRow], theme: ThemeManager, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.rows = list(rows)
        self.outcome = Outcome("", None)
        self.setWindowTitle(TITLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(720, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel(TITLE), "dialogTitle"))
        self.table = self._table(theme)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.variables: list[QPushButton] = []
        for row in self.rows:
            if row.energy_ry is None:
                continue
            button = QPushButton(f"E({row.name})")
            button.setProperty(VARIABLE, f"E({row.name})")
            button.setToolTip(_("Inserir na equação"))
            button.setAutoDefault(False)  # Enter in the equation saves, it never inserts
            button.clicked.connect(self._insert_variable)
            buttons.addWidget(button)
            self.variables.append(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.equation = QLineEdit(default_equation(self.rows))
        self.equation.setFont(mono_font(12))
        self.equation.setPlaceholderText(_("E_ads = E(complexo) - E(substrato) - E(adsorvato)"))
        layout.addWidget(self.equation)
        self.result_label = QLabel()
        self.result_label.setFont(mono_font(12))
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_label)
        self.error = set_variant(QLabel(), "dialogError")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.close_button = QPushButton(_("Fechar"))
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.close)
        self.save_button = set_variant(QPushButton(_("Salvar resultado")), "primary")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.close_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        self.equation.textChanged.connect(self._update)
        self._update()
        self.equation.setFocus()
        self.equation.end(False)

    def _table(self, theme: ThemeManager) -> QTableWidget:
        table = QTableWidget(len(self.rows), len(HEADERS))
        table.setHorizontalHeaderLabels(list(HEADERS))
        table.verticalHeader().setVisible(False)  # type: ignore[union-attr]
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        muted = QBrush(theme.color("text_meta"))  # informative text: never the disabled colour
        for r, row in enumerate(self.rows):
            energy = f"{row.energy_ry:.8f}" if row.energy_ry is not None else "—"
            atoms = "" if row.atoms is None else str(row.atoms)
            cells = (role_label(row.role), row.name, row.path.name, atoms, energy)
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c >= 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if row.problem:
                    item.setForeground(muted)
                    item.setToolTip(row.problem)
                else:
                    item.setToolTip(str(row.path))
                table.setItem(r, c, item)
        return table

    def _insert_variable(self) -> None:
        button = self.sender()
        if isinstance(button, QPushButton):
            self.insert_variable(str(button.property(VARIABLE)))

    def insert_variable(self, text: str) -> None:
        """``text`` at the cursor (over the selection), the focus back on the equation."""
        self.equation.insert(text)
        self.equation.setFocus()

    def _update(self) -> None:
        self.outcome = calculate(self.equation.text(), self.rows)
        ok = self.outcome.value_ry is not None
        self.result_label.setText(self.outcome.text if ok else "")
        self.result_label.setVisible(ok)
        self.error.setText("" if ok else self.outcome.text)
        self.error.setVisible(not ok)
        self.save_button.setEnabled(ok)
        self.save_button.setToolTip("" if ok else self.outcome.text)

    def _save(self) -> None:
        if self.outcome.value_ry is not None:
            self.save_requested.emit(self, self.equation.text())

    def done(self, result: int) -> None:
        self.closed.emit(self)
        super().done(result)
