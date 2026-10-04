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

from ...core.plotting.grid import MAX_SIZE, GridCell, PlotRef

HEADERS = ("Gráfico", "Linha", "Coluna", "Título")
MISSING = " (pasta não encontrada)"


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
        self.verticalHeader().setVisible(False)  # type: ignore[union-attr]
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
        """The open plots to offer; every row keeps the plot it has."""
        self._choices = list(choices)
        for row in range(self.rowCount()):
            self._fill(self.combo(row), self.combo(row).currentData())

    def set_limits(self, rows: int, cols: int) -> None:
        """Rows and columns of the grid: the position spinboxes go no further."""
        self._limits = (rows, cols)
        for row in range(self.rowCount()):
            self.spin(row, 1).setMaximum(rows)
            self.spin(row, 2).setMaximum(cols)

    def set_cells(self, cells: list[GridCell]) -> None:
        self.setRowCount(0)
        for cell in cells:
            self.add_cell(cell)
        self.changed.emit()

    def add_cell(self, cell: GridCell | None = None) -> None:
        """A row for ``cell``, or for a new one: the first free position and the first open plot
        no row shows yet."""
        if cell is None:
            cell = self._new_cell()
        row = self.rowCount()
        self.insertRow(row)
        combo = QComboBox()
        self._fill(combo, cell.ref)
        combo.currentIndexChanged.connect(self.changed)
        self.setCellWidget(row, 0, combo)
        for column, (value, limit) in enumerate(
            zip((cell.row, cell.col), self._limits, strict=True), 1
        ):
            spin = QSpinBox()
            spin.setRange(1, limit)
            spin.setValue(value + 1)
            spin.valueChanged.connect(self.changed)
            self.setCellWidget(row, column, spin)
        title = QLineEdit(cell.title)
        title.setPlaceholderText("o do gráfico")
        title.textChanged.connect(self.changed)
        self.setCellWidget(row, 3, title)
        self.changed.emit()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        if not rows and self.currentRow() >= 0:
            rows = [self.currentRow()]
        for row in rows:
            self.removeRow(row)
        self.changed.emit()

    def _new_cell(self) -> GridCell:
        rows, cols = self._limits
        cells = self.cells()
        taken = {(c.row, c.col) for c in cells}
        free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in taken]
        row, col = free[0] if free else (min(len(cells) // MAX_SIZE, rows - 1), 0)
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
