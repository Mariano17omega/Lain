"""A table of atoms with a checkbox each, to pick some of them (spec 21 R4, spec 30 R3).

It is the table of the PDOS atom window and of the "Átomos" tab of "Criar cálculo". It knows no file and no
module: it gets the rows as text (what each caller wants shown, in its own unit) and says which atom
numbers are marked. A row may carry a note: the "Sítio" column shows only when some row has one (spec 42:
the surface candidates), and ``set_rows`` swaps the rows keeping the marks of the atoms still listed.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from typing import NamedTuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from ..painting import mono_font
from .common import set_variant

COUNT_FORMAT = "{n} de {m} átomos"
COORDINATE_WIDTH = 96
STRETCH = QHeaderView.ResizeMode.Stretch


class AtomRow(NamedTuple):
    index: int  # the atom's number (1-based)
    species: str
    x: str  # the coordinates as they are shown
    y: str
    z: str
    note: str = ""  # the "Sítio" column (shown only when some row has a note)


class AtomTable(QWidget):
    changed = pyqtSignal()  # the marks changed (once per button, once per click)

    def __init__(
        self,
        rows: Sequence[AtomRow],
        selected: Collection[int] | None = None,
        unit: str = "Å",
        count_format: str = COUNT_FORMAT,
        parent: QWidget | None = None,
    ):
        """``selected``: the atoms marked at the start (None: all). ``unit`` heads the coordinates;
        ``count_format`` has ``{n}`` (marked) and ``{m}`` (all)."""
        super().__init__(parent)
        self.rows = sorted(rows, key=lambda row: row.index)
        self.unit = unit
        self.count_format = count_format
        self.checks: dict[int, QCheckBox] = {}  # by atom number
        self._quiet = False  # a button flips many marks: one ``changed`` at its end

        self.mark_all = QPushButton("Marcar todos")
        self.unmark_all = QPushButton("Desmarcar todos")
        self.invert = QPushButton("Inverter")
        self.species_button = QPushButton("Só espécie ▸")
        self.species_menu = QMenu(self.species_button)
        self._fill_menu()
        self.species_button.setMenu(self.species_menu)
        tools = QHBoxLayout()
        for button in (self.mark_all, self.unmark_all, self.invert, self.species_button):
            button.setAutoDefault(False)
            tools.addWidget(button)
        tools.addStretch(1)

        self.table = QTableWidget()
        self._setup_table()
        self._fill(selected)
        self.count = set_variant(QLabel(), "dialogText")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(tools)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.count)
        self.mark_all.clicked.connect(lambda: self.set_all(True))
        self.unmark_all.clicked.connect(lambda: self.set_all(False))
        self.invert.clicked.connect(self.invert_marks)
        self._update_count()

    # -- table ---------------------------------------------------------------------------------
    @property
    def has_notes(self) -> bool:
        return any(row.note for row in self.rows)

    def headers(self) -> tuple[str, ...]:
        coordinates = tuple(f"{axis} ({self.unit})" for axis in "xyz")
        return ("", "#", "Elemento", *coordinates, *(("Sítio",) if self.has_notes else ()))

    def _setup_table(self) -> None:
        table = self.table
        table.setObjectName("atomsTable")
        table.setMinimumHeight(180)
        vertical = table.verticalHeader()
        assert vertical is not None
        vertical.setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)

    def _fill_menu(self) -> None:
        self.species_menu.clear()
        for name in dict.fromkeys(row.species for row in self.rows):
            action = self.species_menu.addAction(name)
            if action is not None:
                action.triggered.connect(lambda _c=False, n=name: self.only_species(n))

    def _fill(self, selected: Collection[int] | None) -> None:
        """The rows of ``self.rows``, the atoms of ``selected`` marked (None: all)."""
        table = self.table
        headers = self.headers()
        table.clearContents()
        table.setRowCount(len(self.rows))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        header = table.horizontalHeader()
        assert header is not None
        for column in range(len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        # The widest text stretches: the element's name, or the note when there is one.
        header.setSectionResizeMode(len(headers) - 1 if self.has_notes else 2, STRETCH)
        for column in range(3, 6):  # same width for the three coordinates
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(column, COORDINATE_WIDTH)
        chosen = None if selected is None else set(selected)
        self.checks = {}
        for row_number, row in enumerate(self.rows):
            check = QCheckBox()
            check.setAccessibleName(f"Átomo {row.index} {row.species}")
            check.setChecked(chosen is None or row.index in chosen)
            check.toggled.connect(self._toggled)
            self.checks[row.index] = check
            cell = QWidget()
            box = QHBoxLayout(cell)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(check, 0, Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row_number, 0, cell)
            values = (str(row.index), row.species, row.x, row.y, row.z, row.note)
            for column, text in enumerate(values[: len(headers) - 1], start=1):
                item = QTableWidgetItem(text)
                item.setFont(mono_font(11))
                right = 2 < column < 6
                align = Qt.AlignmentFlag.AlignVCenter | (
                    Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
                )
                item.setTextAlignment(int(align))
                table.setItem(row_number, column, item)

    def set_rows(self, rows: Sequence[AtomRow]) -> bool:
        """Show ``rows`` instead; the atoms marked that are still listed stay marked. Says
        ``changed`` once (and returns True) when the marks changed."""
        before = self.checked()
        self.rows = sorted(rows, key=lambda row: row.index)
        self._fill_menu()
        self._fill(before)
        self._update_count()
        moved = self.checked() != before
        if moved:
            self.changed.emit()
        return moved

    # -- marks ---------------------------------------------------------------------------------
    def checked(self) -> list[int]:
        """The marked atom numbers, ascending."""
        return [index for index, check in sorted(self.checks.items()) if check.isChecked()]

    def value(self) -> tuple[int, ...]:
        return tuple(self.checked())

    def set_all(self, on: bool) -> None:
        self._flip(lambda _index, _was: on)

    def invert_marks(self) -> None:
        self._flip(lambda _index, was: not was)

    def only_species(self, species: str) -> None:
        wanted = {row.index for row in self.rows if row.species == species}
        self._flip(lambda index, _was: index in wanted)

    def _flip(self, new_state: Callable[[int, bool], bool]) -> None:
        self._quiet = True
        try:
            for index, check in self.checks.items():
                check.setChecked(new_state(index, check.isChecked()))
        finally:
            self._quiet = False
        self._toggled()

    def _toggled(self, *_args) -> None:
        if self._quiet:
            return
        self._update_count()
        self.changed.emit()

    def _update_count(self) -> None:
        self.count.setText(self.count_format.format(n=len(self.checked()), m=len(self.checks)))
