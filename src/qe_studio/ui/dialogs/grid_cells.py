"""The cells table of the "Grids" window (spec 23 R3.3): plot, row, column and title of each cell."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QWidget,
)

from ...core.plotting.grid import GridCell, PlotRef
from ...i18n import _
from ..widgets.common import hide_vertical_header
from ..widgets.no_wheel import NoWheelComboBox, NoWheelSpinBox

HEADERS = (_("Gráfico"), _("Linha"), _("Coluna"), _("Título"))
MISSING = _(" (pasta não encontrada)")


@dataclass(frozen=True)
class PlotChoice:
    """A plot the combo offers: an open plot tab, or the plot a saved grid names."""

    label: str
    ref: PlotRef
    missing: bool = False  # its folder (or file) is not there: drawn as "Plot indisponível"

    @property
    def text(self) -> str:
        return self.label + (MISSING if self.missing else "")


class CellsTable(QTableWidget):
    """One row per cell; positions are shown from 1 and limited to the grid's rows and columns."""

    changed = pyqtSignal()

    def __init__(self, describe: Callable[[PlotRef], PlotChoice], parent: QWidget | None = None):
        super().__init__(0, len(HEADERS), parent)
        self.setObjectName("gridCellsTable")
        self._describe = describe
        self._choices: list[PlotChoice] = []
        self._limits = (1, 1)
        self.setHorizontalHeaderLabels(list(HEADERS))
        hide_vertical_header(self)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    # -- reading -------------------------------------------------------------------------------
    def cells(self) -> list[GridCell]:
        return [self._cell(row) for row in range(self.rowCount())]

    def combo(self, row: int) -> QComboBox:
        widget = self.cellWidget(row, 0)
        assert isinstance(widget, QComboBox)
        return widget

    def spin(self, row: int, column: int) -> QSpinBox:
        widget = self.cellWidget(row, column)
        assert isinstance(widget, QSpinBox)
        return widget

    def title_edit(self, row: int) -> QLineEdit:
        widget = self.cellWidget(row, 3)
        assert isinstance(widget, QLineEdit)
        return widget

    def _cell(self, row: int) -> GridCell:
        ref = self.combo(row).currentData()
        return GridCell(
            self.spin(row, 1).value() - 1,
            self.spin(row, 2).value() - 1,
            ref if isinstance(ref, PlotRef) else None,
            self.title_edit(row).text(),
        )

    # -- changes -------------------------------------------------------------------------------
    def set_choices(self, choices: list[PlotChoice]) -> None:
        """The open plots to offer; every row keeps the plot it has. The rows' plots may have
        changed meaning (a cell with no plot now has one, a tab was renamed): ``changed``."""
        self._choices = list(choices)
        for row in range(self.rowCount()):
            self._fill(self.combo(row), self.combo(row).currentData())
        if self.rowCount():
            self.changed.emit()

    def set_limits(self, rows: int, cols: int) -> None:
        """Rows and columns of the grid: the position spinboxes go no further."""
        self._limits = (rows, cols)
        for row in range(self.rowCount()):
            self.spin(row, 1).setMaximum(rows)
            self.spin(row, 2).setMaximum(cols)

    def set_cells(self, cells: list[GridCell]) -> None:
        """Replace every row; ``changed`` once, not once per row."""
        self.setRowCount(0)
        for cell in cells:
            self.add_cell(cell, notify=False)
        self.changed.emit()

    def has_free_position(self) -> bool:
        """Some position of the grid has no cell yet (a new one has somewhere to go)."""
        return bool(self._free_positions(self.cells()))

    def add_cell(self, cell: GridCell | None = None, notify: bool = True) -> None:
        """A row for ``cell``, or for a new one: the first free position and the first open plot
        no row shows yet (nothing is added when every position is taken)."""
        if cell is None:
            cell = self._new_cell()
            if cell is None:
                return
        row = self.rowCount()
        self.insertRow(row)
        combo = NoWheelComboBox()
        self._fill(combo, cell.ref)
        combo.currentIndexChanged.connect(self.changed)
        self.setCellWidget(row, 0, combo)
        for column, (value, limit) in enumerate(
            zip((cell.row, cell.col), self._limits, strict=True), 1
        ):
            spin = NoWheelSpinBox()
            spin.setRange(1, limit)
            spin.setValue(value + 1)
            spin.valueChanged.connect(self.changed)
            self.setCellWidget(row, column, spin)
        title = QLineEdit(cell.title)
        title.setPlaceholderText(_("o do gráfico"))
        title.textChanged.connect(self.changed)
        self.setCellWidget(row, 3, title)
        if notify:
            self.changed.emit()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        if not rows and self.currentRow() >= 0:
            rows = [self.currentRow()]
        for row in rows:
            self.removeRow(row)
        self.changed.emit()

    def _free_positions(self, cells: list[GridCell]) -> list[tuple[int, int]]:
        """The positions of the grid no cell has, row by row."""
        rows, cols = self._limits
        taken = {(c.row, c.col) for c in cells}
        return [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in taken]

    def _new_cell(self) -> GridCell | None:
        """The cell for the first free position (None: there is none) with the first plot no row
        shows yet."""
        cells = self.cells()
        free = self._free_positions(cells)
        if not free:
            return None
        row, col = free[0]
        used = {c.ref for c in cells}
        ref = next((c.ref for c in self._choices if c.ref not in used), None)
        if ref is None and self._choices:
            ref = self._choices[0].ref
        return GridCell(row, col, ref)

    def _fill(self, combo: QComboBox, ref: PlotRef | None) -> None:
        """The open plots, plus ``ref`` when no open plot is it (a saved grid's)."""
        choices = list(self._choices)
        if ref is not None and all(c.ref != ref for c in choices):
            choices.append(self._describe(ref))
        combo.blockSignals(True)
        combo.clear()
        for choice in choices:
            combo.addItem(choice.text, choice.ref)
            tip = "\n".join(str(path) for path in choice.ref.paths)
            combo.setItemData(combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        index = next((i for i, c in enumerate(choices) if c.ref == ref), 0 if choices else -1)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
