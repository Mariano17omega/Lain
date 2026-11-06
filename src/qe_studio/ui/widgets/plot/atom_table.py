"""A table of atoms with a checkbox each, to pick some of them (spec 21 R4, spec 30 R3).

It is the table of the PDOS atom window and of the "Átomos" tab of "Criar cálculo". It knows no file and no
module: it gets the rows as text (what each caller wants shown, in its own unit) and says which atom
numbers are marked. A row may carry a note: the note column ("Sítio" unless the caller names it) shows
only when some row has one (spec 42: the surface candidates), and ``set_rows`` swaps the rows keeping
the marks of the atoms still listed, or taking the marks it is given (spec 76).

"Só espécie" marks one species, or, with ``species_filter`` (spec 87 R5: a list too long to read), only
shows its rows: the marks stay, and those it hides are still marked, which the count says.
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

from ....i18n import _, ngettext
from ..common import set_variant
from ..painting import mono_font

COUNT_FORMAT = _("{n} de {m} átomos")
NOTE_HEADER = _("Sítio")
COORDINATE_WIDTH = 96
STRETCH = QHeaderView.ResizeMode.Stretch


class AtomRow(NamedTuple):
    index: int  # the atom's number (1-based)
    species: str
    x: str  # the coordinates as they are shown
    y: str
    z: str
    note: str = ""  # the note column (shown only when some row has a note)


class AtomTable(QWidget):
    changed = pyqtSignal()  # the marks changed (once per button, once per click)

    def __init__(
        self,
        rows: Sequence[AtomRow],
        selected: Collection[int] | None = None,
        unit: str = "Å",
        count_format: str = COUNT_FORMAT,
        parent: QWidget | None = None,
        *,
        check_header: str = "",
        note_header: str = NOTE_HEADER,
        species_filter: bool = False,
    ):
        """``selected``: the atoms marked at the start (None: all). ``unit`` heads the coordinates;
        ``count_format`` has ``{n}`` (marked) and ``{m}`` (all); the headers title the checkbox and
        note columns; ``species_filter``: the species menu shows rows instead of marking them."""
        super().__init__(parent)
        self.rows = sorted(rows, key=lambda row: row.index)
        self.unit = unit
        self.count_format = count_format
        self.check_header, self.note_header = check_header, note_header
        self.species_filter = species_filter
        self.shown_species = ""  # the rows in view, with ``species_filter`` ("": all of them)
        self.checks: dict[int, QCheckBox] = {}  # by atom number
        self._quiet = False  # a button flips many marks: one ``changed`` at its end

        self.mark_all = QPushButton(_("Marcar todos"))
        self.unmark_all = QPushButton(_("Desmarcar todos"))
        self.invert = QPushButton(_("Inverter"))
        self.species_button = QPushButton(_("Só espécie ▸"))
        self.species_menu = QMenu(self.species_button)
        self._fill_menu()
        self.species_button.setMenu(self.species_menu)
        if species_filter:
            self.species_button.setToolTip(
                _("Mostrar só os átomos de uma espécie; as marcas não mudam")
            )
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
        notes = (self.note_header,) if self.has_notes else ()
        return (self.check_header, "#", _("Elemento"), *coordinates, *notes)

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
        if self.species_filter:
            action = self.species_menu.addAction(_("Todas"))
            if action is not None:
                action.triggered.connect(lambda _c=False: self.show_species(""))
        pick = self.show_species if self.species_filter else self.only_species
        for name in dict.fromkeys(row.species for row in self.rows):
            action = self.species_menu.addAction(name)
            if action is not None:
                action.triggered.connect(lambda _c=False, n=name: pick(n))

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
            check.setAccessibleName(
                _("Átomo {index} {species}").format(index=row.index, species=row.species)
            )
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
        self._apply_filter()

    def set_rows(self, rows: Sequence[AtomRow], marks: Collection[int] | None = None) -> bool:
        """Show ``rows`` instead, the atoms of ``marks`` marked (None: those marked that are still
        listed stay marked). Says ``changed`` once (and returns True) when the marks changed."""
        before = self.checked()
        self.rows = sorted(rows, key=lambda row: row.index)
        if self.shown_species not in {row.species for row in self.rows}:
            self.shown_species = ""
        self._fill_menu()
        self._fill(before if marks is None else marks)
        self._update_count()
        moved = self.checked() != before
        if moved:
            self.changed.emit()
        return moved

    # -- filter --------------------------------------------------------------------------------
    def show_species(self, species: str) -> None:
        """Only the rows of ``species`` stay in view ("": all). No mark changes and no ``changed`` is
        said: what the plan reads is the marks, not the list."""
        self.shown_species = species
        self._apply_filter()
        self._update_count()

    def _listed(self) -> set[int]:
        """The atoms in view."""
        shown = self.shown_species
        return {row.index for row in self.rows if not shown or row.species == shown}

    def _apply_filter(self) -> None:
        """Row by row: Qt keeps the hidden flag of a row number across ``setRowCount``."""
        listed = self._listed()
        for row_number, row in enumerate(self.rows):
            self.table.setRowHidden(row_number, row.index not in listed)
        shown = self.shown_species
        self.species_button.setText(
            _("Só espécie: {species} ▸").format(species=shown) if shown else _("Só espécie ▸")
        )

    # -- marks ---------------------------------------------------------------------------------
    def checked(self) -> list[int]:
        """The marked atom numbers, ascending."""
        return [index for index, check in sorted(self.checks.items()) if check.isChecked()]

    def value(self) -> tuple[int, ...]:
        return tuple(self.checked())

    def set_all(self, on: bool) -> None:
        """Mark the rows in view, or unmark every row: the direct way out of a mark the filter hides."""
        listed = self._listed()
        self._flip(lambda index, was: on and (was or index in listed))

    def invert_marks(self) -> None:
        """Invert the rows in view."""
        listed = self._listed()
        self._flip(lambda index, was: (not was) if index in listed else was)

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
        marked = self.checked()
        text = self.count_format.format(n=len(marked), m=len(self.checks))
        listed = self._listed()
        outside = sum(index not in listed for index in marked)
        if outside:
            hidden = ngettext(
                "{n} marcado fora do filtro", "{n} marcados fora do filtro", outside
            ).format(n=outside)
            text = f"{text}; {hidden}"
        self.count.setText(text)
