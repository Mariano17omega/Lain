"""Left panel: tab container plus the "Átomo" and "Célula" tabs."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from viewer3d.core.bonds import BondGraph
from viewer3d.core.elements import element_for_label
from viewer3d.core.structure import AtomRef, Structure
from viewer3d.ui.canvas import Canvas
from viewer3d.ui.panel_display import DisplayTab
from viewer3d.ui.panel_measures import MeasuresTab

NEIGHBOR_LIMIT = 12
DASH = "—"


def atom_title(structure: Structure, ref: AtomRef) -> str:
    """``#12 Si`` style name of an atom copy (1-based, as QE numbers atoms)."""
    return f"#{ref.index + 1} {structure.symbols[ref.index]}"


def image_text(ref: AtomRef) -> str:
    return DASH if ref.shift == (0, 0, 0) else f"({ref.shift[0]}, {ref.shift[1]}, {ref.shift[2]})"


def _value_label() -> QLabel:
    label = QLabel(DASH)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(True)
    return label


class AtomTab(QWidget):
    neighbor_clicked = pyqtSignal(object)  # AtomRef

    FIELDS = (
        ("number", "Nº"),
        ("label", "Rótulo da espécie"),
        ("element", "Elemento"),
        ("z", "Z"),
        ("mass", "Massa (u)"),
        ("pseudo", "Pseudopotencial"),
        ("cart", "Posição (Å)"),
        ("frac", "Fracionária"),
        ("image", "Imagem"),
        ("flags", "if_pos"),
        ("magnetization", "starting_magnetization"),
        ("hubbard", "Hubbard_U (eV)"),
        ("coordination", "Coordenação"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._neighbors: list[AtomRef] = []
        self._placeholder = QLabel("Clique em um átomo")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._form_widget = QWidget()
        form = QFormLayout(self._form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        self._rows: dict[str, tuple[QLabel, QLabel]] = {}
        for key, text in self.FIELDS:
            caption, value = QLabel(text + ":"), _value_label()
            form.addRow(caption, value)
            self._rows[key] = (caption, value)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Átomo", "Imagem", "Distância (Å)"])
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.cellClicked.connect(self._row_clicked)
        self._neighbors_caption = QLabel("Vizinhos ligados:")
        layout = QVBoxLayout(self)
        layout.addWidget(self._placeholder)
        layout.addWidget(self._form_widget)
        layout.addWidget(self._neighbors_caption)
        layout.addWidget(self._table, 1)
        self.show_atom(None, None, None)

    def _set(self, key: str, text: str, visible: bool = True) -> None:
        caption, value = self._rows[key]
        value.setText(text)
        caption.setVisible(visible)
        value.setVisible(visible)

    def show_atom(self, structure: Structure | None, graph: BondGraph | None, ref: AtomRef | None):
        has = structure is not None and ref is not None
        self._placeholder.setVisible(not has)
        self._form_widget.setVisible(has)
        self._neighbors_caption.setVisible(has)
        self._table.setVisible(has)
        self._neighbors = []
        self._table.setRowCount(0)
        if not has:
            return
        i = ref.index
        label = structure.labels[i]
        species = structure.species[int(structure.species_index[i])]
        element = element_for_label(label)
        source = structure.source
        position = structure.position(ref)
        frac = structure.frac[i] + ref.shift
        self._set("number", str(i + 1))
        self._set("label", label)
        self._set("element", f"{element.name} ({element.symbol})" if element.known else DASH)
        self._set("z", str(element.z) if element.known else DASH)
        self._set("mass", f"{species.mass:g}" if species.mass is not None else DASH)
        self._set("pseudo", species.pseudo or DASH)
        self._set("cart", "{:.5f}  {:.5f}  {:.5f}".format(*position))
        self._set("frac", "{:.6f}  {:.6f}  {:.6f}".format(*frac))
        self._set("image", image_text(ref), visible=ref.shift != (0, 0, 0))
        flags = structure.flags[i]
        self._set("flags", DASH if flags is None else " ".join(str(f) for f in flags))
        magnetization = source.starting_magnetization.get(species.number)
        self._set(
            "magnetization",
            "" if magnetization is None else f"{magnetization:g}",
            visible=magnetization is not None,
        )
        hubbard = source.hubbard_u.get(species.number)
        self._set("hubbard", "" if hubbard is None else f"{hubbard:g}", visible=hubbard is not None)
        near = graph.neighbors(ref) if graph is not None else []
        self._set("coordination", str(len(near)))
        shown = near[:NEIGHBOR_LIMIT]
        self._table.setRowCount(len(shown))
        for row, (neighbor, distance) in enumerate(shown):
            self._neighbors.append(neighbor)
            cells = (atom_title(structure, neighbor), image_text(neighbor), f"{distance:.4f}")
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

    def _row_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._neighbors):
            self.neighbor_clicked.emit(self._neighbors[row])


class CellTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        form = QFormLayout()
        self._values: dict[str, QLabel] = {}
        for key, text in (
            ("abc", "a, b, c (Å)"),
            ("angles", "α, β, γ (°)"),
            ("volume", "Volume (Å³)"),
            ("a1", "a₁ (Å)"),
            ("a2", "a₂ (Å)"),
            ("a3", "a₃ (Å)"),
            ("ibrav", "ibrav"),
            ("nat", "nat"),
            ("formula", "Fórmula"),
            ("prefix", "prefix"),
            ("calculation", "calculation"),
        ):
            value = _value_label()
            form.addRow(text + ":", value)
            self._values[key] = value
        self._warnings = QPlainTextEdit()
        self._warnings.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Avisos do leitor:"))
        layout.addWidget(self._warnings, 1)
        self.show_structure(None)

    def show_structure(self, structure: Structure | None) -> None:
        if structure is None:
            for value in self._values.values():
                value.setText(DASH)
            self._warnings.setPlainText("")
            return
        a, b, c, alpha, beta, gamma = structure.lattice_parameters
        v = self._values
        v["abc"].setText(f"{a:.5f}   {b:.5f}   {c:.5f}")
        v["angles"].setText(f"{alpha:.3f}   {beta:.3f}   {gamma:.3f}")
        v["volume"].setText(f"{structure.volume:.4f}")
        for key, row in zip(("a1", "a2", "a3"), structure.cell, strict=True):
            v[key].setText("{:.5f}  {:.5f}  {:.5f}".format(*row))
        source = structure.source
        v["ibrav"].setText(str(source.ibrav))
        v["nat"].setText(str(source.nat))
        v["formula"].setText(structure.formula)
        v["prefix"].setText(source.prefix)
        v["calculation"].setText(source.calculation)
        warnings = source.warnings
        self._warnings.setPlainText("\n".join(warnings) if warnings else "Nenhum aviso.")


class LeftPanel(QTabWidget):
    """The four tabs; it listens to the canvas and never touches the disk."""

    neighbor_clicked = pyqtSignal(object)

    def __init__(self, canvas: Canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self.atom = AtomTab()
        self.measures = MeasuresTab(canvas)
        self.display = DisplayTab(canvas)
        self.cell = CellTab()
        self.addTab(self.atom, "Átomo")
        self.addTab(self.measures, "Medidas")
        self.addTab(self.display, "Exibição")
        self.addTab(self.cell, "Célula")
        self.atom.neighbor_clicked.connect(self.neighbor_clicked)
        canvas.current_changed.connect(self._current_changed)

    def structure_changed(self) -> None:
        structure = self.canvas.structure
        self.cell.show_structure(structure)
        self.display.structure_changed()
        self.measures.structure_changed()
        self.atom.show_atom(None, None, None)

    def _current_changed(self, ref) -> None:
        self.atom.show_atom(self.canvas.structure, self.canvas.graph, ref)
