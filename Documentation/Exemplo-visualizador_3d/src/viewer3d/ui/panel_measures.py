"""The "Medidas" tab: selected atoms, current measurement and the accumulated table."""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from viewer3d.core import measure
from viewer3d.core.structure import AtomRef
from viewer3d.ui.canvas import Canvas

HEADER = ("Medida", "Átomos", "Valor", "Δx (Å)", "Δy (Å)", "Δz (Å)")
KINDS = {2: "Distância (Å)", 3: "Ângulo (°)", 4: "Diedro (°)"}


class MeasuresTab(QWidget):
    def __init__(self, canvas: Canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self._rows: list[tuple[str, ...]] = []
        self._last_count = 0

        self._selected = QTableWidget(0, 3)
        self._selected.setHorizontalHeaderLabels(["Nº", "Átomo", "Imagem"])
        self._selected.verticalHeader().hide()
        self._selected.setMaximumHeight(140)
        self._selected.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._selected.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._current = QLabel("Selecione 2 a 4 átomos (clique; Ctrl+clique alterna).")
        self._current.setWordWrap(True)
        self._table = QTableWidget(0, len(HEADER))
        self._table.setHorizontalHeaderLabels(HEADER)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        copy = QPushButton("Copiar")
        clear = QPushButton("Limpar")
        nearest = QPushButton("Usar imagem mais próxima")
        copy.clicked.connect(self.copy_tsv)
        clear.clicked.connect(self.clear)
        nearest.clicked.connect(self.use_nearest_image)
        buttons = QHBoxLayout()
        buttons.addWidget(copy)
        buttons.addWidget(clear)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Átomos selecionados (ordem do clique):"))
        layout.addWidget(self._selected)
        layout.addWidget(self._current)
        layout.addWidget(nearest)
        layout.addWidget(QLabel("Medidas feitas:"))
        layout.addWidget(self._table, 1)
        layout.addLayout(buttons)
        canvas.selection_changed.connect(self._selection_changed)

    # --- helpers ------------------------------------------------------------------------
    def _name(self, ref: AtomRef) -> str:
        structure = self.canvas.structure
        text = f"{structure.symbols[ref.index]}{ref.index + 1}"
        if ref.shift != (0, 0, 0):
            text += f"({ref.shift[0]},{ref.shift[1]},{ref.shift[2]})"
        return text

    def _measure(self, refs: list[AtomRef]) -> tuple[str, str, str, tuple[str, str, str]] | None:
        structure = self.canvas.structure
        n = len(refs)
        blank = ("", "", "")
        if structure is None or n < 2:
            return None
        names = " – ".join(self._name(r) for r in refs)
        if n == 2:
            result = measure.distance(structure, refs[0], refs[1])
            delta = tuple(f"{x:+.4f}" for x in result.delta)
            return KINDS[2], names, f"{result.value:.4f}", delta  # type: ignore[return-value]
        value = measure.angle(structure, *refs) if n == 3 else measure.dihedral(structure, *refs)
        text = "—" if math.isnan(value) else f"{value:.3f}"
        return KINDS[n], names, text, blank

    # --- slots --------------------------------------------------------------------------
    def structure_changed(self) -> None:
        self._rows.clear()
        self._table.setRowCount(0)
        self._last_count = 0
        self._selection_changed([])

    def _selection_changed(self, refs: list[AtomRef]) -> None:
        structure = self.canvas.structure
        self._selected.setRowCount(len(refs))
        for row, ref in enumerate(refs):
            image = "—" if ref.shift == (0, 0, 0) else str(ref.shift)
            symbol = structure.symbols[ref.index] if structure else "?"
            for col, text in enumerate((str(row + 1), f"#{ref.index + 1} {symbol}", image)):
                self._selected.setItem(row, col, QTableWidgetItem(text))
        measured = self._measure(refs)
        if measured is None:
            self._current.setText("Selecione 2 a 4 átomos (clique; Ctrl+clique alterna).")
        else:
            kind, atoms, value, delta = measured
            extra = f"   (Δ {', '.join(delta)})" if delta[0] else ""
            self._current.setText(f"<b>{kind}:</b> {value}{extra}<br>{atoms}")
            if len(refs) > self._last_count:  # a new atom completed a measurement
                self._append(kind, atoms, value, delta)
        self._last_count = len(refs)

    def _append(self, kind: str, atoms: str, value: str, delta: tuple[str, str, str]) -> None:
        row = (kind, atoms, value, *delta)
        self._rows.append(row)
        index = self._table.rowCount()
        self._table.insertRow(index)
        for col, text in enumerate(row):
            self._table.setItem(index, col, QTableWidgetItem(text))
        self._table.scrollToBottom()

    def use_nearest_image(self) -> None:
        refs, structure = list(self.canvas.selection), self.canvas.structure
        if structure is None or len(refs) < 2:
            return
        refs[-1] = measure.nearest_image(structure, refs[-2], refs[-1])
        self._last_count = len(refs) - 1  # record the corrected measurement as a new row
        self.canvas.set_selection(refs, refs[-1])

    def copy_tsv(self) -> None:
        lines = ["\t".join(HEADER)] + ["\t".join(row) for row in self._rows]
        QApplication.clipboard().setText("\n".join(lines))

    def tsv(self) -> str:
        return "\n".join(["\t".join(HEADER)] + ["\t".join(row) for row in self._rows])

    def clear(self) -> None:
        self._rows.clear()
        self._table.setRowCount(0)
        self._last_count = 0
        self.canvas.set_selection([], None)
