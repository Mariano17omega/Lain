"""The "Átomo" section of the structure panel (spec 43 R5.2): the current atom, named as QE numbers it,
what the input says of it and its bonded neighbours (a click on one selects that copy)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ....core.structure3d.bonds import BondGraph
from ....core.structure3d.elements import element_for_label
from ....core.structure3d.model import AtomRef, Structure, atom_name
from ...theme.scale import scaled
from ..common import set_variant
from ..param_widgets import Section

NEIGHBOR_LIMIT = 12
ROW_PX = 22  # a neighbour row at scale 1
DASH = "—"
PLACEHOLDER = "Clique em um átomo para ver os dados."
FREE = (1, 1, 1)  # pw.x's if_pos when a row writes none

# (key, label, mono): the rows under the title, in order.
ROWS = (
    ("species", "Espécie", False),
    ("element", "Elemento", False),
    ("mass", "Massa", False),
    ("pseudo", "Pseudopotencial", False),
    ("cart", "Posição (Å)", True),
    ("frac", "Fracionária", True),
    ("image", "Imagem", True),
    ("flags", "Fixo (if_pos)", True),
    ("magnetization", "Magnetização inicial", False),
    ("coordination", "Coordenação", False),
)


def element_text(label: str) -> str:
    element = element_for_label(label)
    if not element.known:
        return "Desconhecido"
    return f"{element.name} ({element.symbol}), Z = {element.z}"


def atom_title(structure: Structure, ref: AtomRef) -> str:
    """``O43 · Oxigênio``: the atom's name and its element."""
    return f"{atom_name(structure, ref)} · {element_for_label(structure.labels[ref.index]).name}"


def triple(values, decimals: int) -> str:
    return "  ".join(f"{float(v):.{decimals}f}" for v in values)


def _value(mono: bool) -> QLabel:
    label = set_variant(QLabel(DASH), "readout") if mono else QLabel(DASH)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(True)
    return label


class AtomSection:
    """Fills ``section`` (a ``Section``) and keeps it showing the current atom."""

    def __init__(self, section: Section, structure: Structure):
        self.section, self.structure = section, structure
        self.graph: BondGraph | None = None
        self.placeholder = set_variant(QLabel(PLACEHOLDER), "meta")
        self.placeholder.setWordWrap(True)
        section.add_full(self.placeholder)
        self.title = set_variant(QLabel(), "atomTitle")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        section.add_full(self.title)
        self.rows: dict[str, tuple[QLabel, QLabel]] = {}
        for key, text, mono in ROWS:
            value = _value(mono)
            self.rows[key] = (section.add_row(text, value), value)
        self.neighbors_caption = set_variant(QLabel("Vizinhos ligados"), "fieldLabel")
        section.add_full(self.neighbors_caption)
        self.table = NeighborTable()
        section.add_full(self.table)
        self.more = set_variant(QLabel(), "meta")
        section.add_full(self.more)
        self.show_atom(None)

    def value(self, key: str) -> str:
        """The text of a row ("" when the row is hidden): tests read the panel through it."""
        label, value = self.rows[key]
        return value.text() if not label.isHidden() else ""

    def _set(self, key: str, text: str, visible: bool = True) -> None:
        label, value = self.rows[key]
        value.setText(text)
        label.setVisible(visible)
        value.setVisible(visible)

    def show_atom(self, ref: AtomRef | None, graph: BondGraph | None = None) -> None:
        if graph is not None:
            self.graph = graph
        has = ref is not None
        self.placeholder.setVisible(not has)
        for widget in (self.title, self.neighbors_caption, self.table):
            widget.setVisible(has)
        if ref is None:
            for key in self.rows:
                self._set(key, DASH, visible=False)
            self.more.setVisible(False)
            self.table.show_neighbors([], self.structure)
            return
        structure = self.structure
        index = ref.index
        label = structure.labels[index]
        species = structure.species[int(structure.species_index[index])]
        self.title.setText(atom_title(structure, ref))
        self._set("species", label)
        self._set("element", element_text(label))
        self._set("mass", DASH if species.mass is None else f"{species.mass:g} u")
        self._set("pseudo", species.pseudo or DASH)
        self._set("cart", triple(structure.position(ref), 4))
        self._set("frac", triple(structure.frac[index] + ref.shift, 5))
        self._set("image", "({}, {}, {})".format(*ref.shift), visible=ref.shift != (0, 0, 0))
        flags = structure.flags[index] or FREE
        self._set("flags", " ".join(str(f) for f in flags), visible=structure.has_flags)
        magnetization = structure.source.starting_magnetization.get(species.number)
        self._set(
            "magnetization",
            "" if magnetization is None else f"{magnetization:g}",
            visible=magnetization is not None,
        )
        near = self.graph.neighbors(ref) if self.graph is not None else []
        self._set("coordination", str(len(near)))
        self.table.show_neighbors(near[:NEIGHBOR_LIMIT], structure)
        extra = len(near) - NEIGHBOR_LIMIT
        self.more.setText(f"+{extra}" if extra > 0 else "")
        self.more.setVisible(extra > 0)


class NeighborTable(QTableWidget):
    """Bonded neighbours: "Átomo" and "Distância (Å)"; as tall as its rows, no scroll of its own."""

    neighbor_clicked = pyqtSignal(object)  # AtomRef

    def __init__(self, parent: QWidget | None = None):
        super().__init__(0, 2, parent)
        self.setObjectName("structureNeighbors")
        self.setHorizontalHeaderLabels(["Átomo", "Distância (Å)"])
        vertical = self.verticalHeader()
        if vertical is not None:
            vertical.hide()
            vertical.setDefaultSectionSize(scaled(ROW_PX))
        horizontal = self.horizontalHeader()
        if horizontal is not None:
            horizontal.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.refs: list[AtomRef] = []
        self.cellClicked.connect(self._clicked)

    def show_neighbors(self, near: list[tuple[AtomRef, float]], structure: Structure) -> None:
        self.refs = [ref for ref, _distance in near]
        self.setRowCount(len(near))
        for row, (ref, distance) in enumerate(near):
            for column, text in enumerate((atom_name(structure, ref), f"{distance:.4f}")):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, column, item)
        self._fit_height()

    def _fit_height(self) -> None:
        header = self.horizontalHeader()
        height = (header.sizeHint().height() if header is not None else 0) + 2 * self.frameWidth()
        height += sum(self.rowHeight(row) for row in range(self.rowCount()))
        self.setFixedHeight(height)

    def _clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.refs):
            self.neighbor_clicked.emit(self.refs[row])
