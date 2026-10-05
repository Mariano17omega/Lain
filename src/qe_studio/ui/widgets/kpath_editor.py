"""The band path of "Criar cálculo" (spec 26 R4.3): a table of high-symmetry points the user types.

Rows are the points of ``K_POINTS crystal_b``: label, the three fractional coordinates and the
points to the next one. "Marcar quebra de segmento" makes the path jump from a point to the next
(``X|U``: weight 1). With the SCF's cell (spec 27-2) the table marks the point a collapsing segment
starts at (bands.x gives a step more than 5× the previous one no x extent) and "Distribuir pelo
comprimento" sets the points of each segment from its length. Nothing here suggests a path.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.calc_create.kpath import (
    DEFAULT_NPTS,
    MAX_NPTS,
    KPath,
    KPoint,
    collapse_note,
    collapsed_segments,
    distribute,
)
from ..theme.manager import ThemeManager
from .common import set_variant

COLUMNS = ("Rótulo", "k1", "k2", "k3", "Pontos")
LABEL, K1, K2, K3, NPTS = range(5)
VALUE = Qt.ItemDataRole.UserRole  # the number a cell holds (its text is how it is shown)
BREAK_TEXT = "quebra"
BREAK_TIP = "O caminho salta deste ponto para o próximo (peso 1)"
END_TEXT = "—"
DEFAULT_DENSITY = 25  # points per Å⁻¹ of "Distribuir pelo comprimento"
DISTRIBUTE_TIP = "Ajusta a coluna Pontos ao comprimento de cada segmento (pontos por Å⁻¹)"
NO_CELL_TIP = "Estrutura do SCF não legível"


@dataclass(frozen=True)
class _Row:
    label: str
    frac: tuple[float, float, float]
    npts: int
    jump: bool = False  # the path breaks after this point


def _number_text(value: float) -> str:
    return f"{value + 0.0:.8g}"  # + 0.0: no "-0"


def _path_of(rows: list[_Row]) -> KPath:
    points = tuple(KPoint(row.label, row.frac, row.npts) for row in rows)
    return KPath(points, frozenset(i for i, row in enumerate(rows) if row.jump))


class KPathEditor(QWidget):
    changed = pyqtSignal(bool)  # the path changed; True when the user did it (not ``set_path``)

    def __init__(
        self,
        theme: ThemeManager,
        cell: np.ndarray | None = None,
        parent: QWidget | None = None,
    ):
        """``cell``: rows a1 a2 a3 in Å of the SCF's structure; None when it could not be read."""
        super().__init__(parent)
        self._theme, self._cell = theme, cell
        self._filling = False
        theme.theme_changed.connect(self.refresh_marks)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("kpathTable")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        points = self.table.horizontalHeaderItem(NPTS)
        if points is not None:
            points.setToolTip("Pontos até o próximo ponto do caminho")
        self.table.setMinimumHeight(
            260
        )  # a whole fcc path (about 12 points) without scrolling much
        vertical = self.table.verticalHeader()
        assert vertical is not None
        vertical.setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(self._update_buttons)

        self.add_button = QPushButton("Adicionar")
        self.remove_button = QPushButton("Remover")
        self.up_button = QPushButton("Subir")
        self.down_button = QPushButton("Descer")
        self.break_button = QPushButton("Marcar quebra de segmento")
        self.break_button.setToolTip(BREAK_TIP)
        self.density = QSpinBox()
        self.density.setRange(1, 500)
        self.density.setValue(DEFAULT_DENSITY)
        self.density.setAccessibleName("Pontos por Å⁻¹")
        self.density.setToolTip("Pontos por Å⁻¹ de comprimento do segmento")
        self.distribute_button = QPushButton("Distribuir pelo comprimento")
        self.add_button.clicked.connect(self.add_point)
        self.remove_button.clicked.connect(self.remove_point)
        self.up_button.clicked.connect(partial(self.move_point, -1))
        self.down_button.clicked.connect(partial(self.move_point, 1))
        self.break_button.clicked.connect(self.toggle_break)
        self.distribute_button.clicked.connect(self.distribute_by_length)
        self.message = set_variant(QLabel(), "dialogWarning")
        self.message.setWordWrap(True)
        self.message.hide()

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        more = QHBoxLayout()
        more.setContentsMargins(0, 0, 0, 0)
        self.break_button.setAutoDefault(False)
        more.addWidget(self.break_button)
        more.addStretch(1)
        layout.addLayout(more)
        spread = QHBoxLayout()
        spread.setContentsMargins(0, 0, 0, 0)
        self.distribute_button.setAutoDefault(False)
        spread.addWidget(QLabel("Pontos por Å⁻¹"))
        spread.addWidget(self.density)
        spread.addWidget(self.distribute_button)
        spread.addStretch(1)
        layout.addLayout(spread)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message)
        self._update_buttons()

    # -- value --------------------------------------------------------------------------------
    def value(self) -> KPath:
        """The path as typed (no points: an empty path, which the type reports as too short)."""
        return _path_of(self._rows())

    def set_path(self, path: KPath) -> None:
        """Show ``path``: not a user edit."""
        rows = [
            _Row(point.label, point.frac, min(max(int(point.npts), 1), MAX_NPTS), i in path.breaks)
            for i, point in enumerate(path.points)
        ]
        self._set_rows(rows, 0 if rows else -1)
        self.changed.emit(False)

    # -- rows -----------------------------------------------------------------------------------
    def _rows(self) -> list[_Row]:
        rows = []
        for row in range(self.table.rowCount()):
            label = self.table.item(row, LABEL)
            values = [self._number(row, column) for column in (K1, K2, K3)]
            npts = self._number(row, NPTS)
            rows.append(
                _Row(
                    label.text().strip() if label is not None else "",
                    (values[0], values[1], values[2]),
                    max(int(npts), 1),
                    self._jump(row),
                )
            )
        return rows

    def _jump(self, row: int) -> bool:
        label = self.table.item(row, LABEL)
        return bool(label is not None and label.data(Qt.ItemDataRole.UserRole + 1))

    def _number(self, row: int, column: int) -> float:
        item = self.table.item(row, column)
        value = item.data(VALUE) if item is not None else None
        return float(value) if value is not None else 0.0

    def _set_rows(self, rows: list[_Row], current: int) -> None:
        self._filling = True
        try:
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                label = QTableWidgetItem(row.label)
                label.setData(Qt.ItemDataRole.UserRole + 1, row.jump)
                self.table.setItem(index, LABEL, label)
                for column, value in zip((K1, K2, K3), row.frac, strict=True):
                    item = QTableWidgetItem(_number_text(value))
                    item.setData(VALUE, float(value))
                    self.table.setItem(index, column, item)
                npts = QTableWidgetItem()
                npts.setData(VALUE, row.npts)
                self.table.setItem(index, NPTS, npts)
            self._show_npts()
        finally:
            self._filling = False
        self.refresh_marks()
        if 0 <= current < len(rows):
            self.table.setCurrentCell(current, LABEL)
        self._update_buttons()

    def _show_npts(self) -> None:
        """The points cell says "quebra" at a jump and "—" at the end, where it does not count."""
        last = self.table.rowCount() - 1
        for row in range(self.table.rowCount()):
            item = self.table.item(row, NPTS)
            if item is None or self.table.item(row, LABEL) is None:
                continue
            jump = self._jump(row)
            flags = item.flags()
            if row == last or jump:
                item.setText(END_TEXT if row == last else BREAK_TEXT)
                item.setToolTip(self._npts_tip(row))
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsEditable)
            else:
                item.setText(str(int(item.data(VALUE))))
                item.setToolTip("")
                item.setFlags(flags | Qt.ItemFlag.ItemIsEditable)

    def _npts_tip(self, row: int) -> str:
        return BREAK_TIP if row != self.table.rowCount() - 1 and self._jump(row) else ""

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling:
            return
        column = item.column()
        if column != LABEL:
            self._filling = True
            try:
                self._take_number(item, column)
            finally:
                self._filling = False
        self._edited()

    def _take_number(self, item: QTableWidgetItem, column: int) -> None:
        """Keep a valid number (comma or dot, finite; points: an integer of 1 to ``MAX_NPTS``);
        put the previous one back otherwise."""
        text = item.text().strip().replace(",", ".")
        previous = item.data(VALUE)
        try:
            if "_" in text:  # Python reads 1_0 as 10
                raise ValueError
            number: float = float(text) if column != NPTS else int(text)
            if not math.isfinite(number) or (column == NPTS and not 1 <= number <= MAX_NPTS):
                raise ValueError
        except ValueError:
            self._show_message(f"Valor inválido: {item.text().strip() or 'vazio'}")
            number = previous
        else:
            self._show_message("")
        item.setData(VALUE, number)
        item.setText(_number_text(number) if column != NPTS else str(int(number)))

    def _edited(self) -> None:
        self.refresh_marks()
        self._update_buttons()
        self.changed.emit(True)

    def _mutate(self, change: Callable[[list[_Row], int], int]) -> None:
        """Apply ``change(rows, current) -> new current`` and show the result: a user edit."""
        rows = self._rows()
        current = change(rows, self.table.currentRow())
        self._set_rows(rows, current)
        self._edited()

    # -- buttons --------------------------------------------------------------------------------
    def add_point(self) -> None:
        def add(rows: list[_Row], current: int) -> int:
            at = current + 1 if 0 <= current < len(rows) else len(rows)
            new = _Row("", (0.0, 0.0, 0.0), DEFAULT_NPTS)
            if 0 <= current < len(rows) and rows[current].jump:
                # The new point continues the segment of the selected one and the break stays
                # where the user put it: before the point that came next.
                new = replace(new, jump=True)
                rows[current] = replace(rows[current], jump=False)
            rows.insert(at, new)
            return at

        self._mutate(add)

    def remove_point(self) -> None:
        def remove(rows: list[_Row], current: int) -> int:
            if not 0 <= current < len(rows):
                return current
            if rows[current].jump and current > 0:
                rows[current - 1] = replace(rows[current - 1], jump=True)  # the break survives
            del rows[current]
            if rows:  # nothing follows the last point: no break there
                rows[-1] = replace(rows[-1], jump=False)
            return min(current, len(rows) - 1)

        self._mutate(remove)

    def move_point(self, delta: int) -> None:
        def move(rows: list[_Row], current: int) -> int:
            target = current + delta
            if not (0 <= current < len(rows) and 0 <= target < len(rows)):
                return current
            rows[current], rows[target] = rows[target], rows[current]
            return target

        self._mutate(move)

    def toggle_break(self) -> None:
        def toggle(rows: list[_Row], current: int) -> int:
            if 0 <= current < len(rows) - 1:  # the last point has nothing after it
                rows[current] = replace(rows[current], jump=not rows[current].jump)
            return current

        self._mutate(toggle)

    def distribute_by_length(self) -> None:
        """ "Distribuir pelo comprimento": only the points column changes."""
        cell, density = self._cell, float(self.density.value())
        if cell is None or self.table.rowCount() < 2:
            return

        def spread(rows: list[_Row], current: int) -> int:
            for i, point in enumerate(distribute(_path_of(rows), cell, density).points):
                rows[i] = replace(rows[i], npts=point.npts)
            return current

        self._mutate(spread)

    def _update_buttons(self, *_args) -> None:
        count, current = self.table.rowCount(), self.table.currentRow()
        selected = 0 <= current < count
        self.remove_button.setEnabled(selected)
        self.up_button.setEnabled(selected and current > 0)
        self.down_button.setEnabled(selected and current < count - 1)
        self.break_button.setEnabled(selected and current < count - 1)
        self.distribute_button.setEnabled(self._cell is not None and count >= 2)
        self.distribute_button.setToolTip(DISTRIBUTE_TIP if self._cell is not None else NO_CELL_TIP)

    # -- marks ------------------------------------------------------------------------------------
    def refresh_marks(self, *_args) -> None:
        """Mark the row each collapsed segment starts at: warning color and the note as tooltip."""
        if self._cell is None:
            return
        path = self.value()
        notes = {seg.a: collapse_note(path, seg) for seg in collapsed_segments(path, self._cell)}
        brush = QBrush(self._theme.color("warning"))
        was, self._filling = self._filling, True  # setting a role emits itemChanged
        try:
            for row in range(self.table.rowCount()):
                note = notes.get(row)
                for column in range(len(COLUMNS)):
                    item = self.table.item(row, column)
                    if item is None:
                        continue
                    item.setForeground(brush if note else QBrush())
                    item.setToolTip(note or (self._npts_tip(row) if column == NPTS else ""))
        finally:
            self._filling = was

    def _show_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))
