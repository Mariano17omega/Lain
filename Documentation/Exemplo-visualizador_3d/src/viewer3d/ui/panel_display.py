"""The "Exibição" tab: every control only edits ``DisplayOptions`` and asks for a repaint."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from viewer3d.core.elements import element_for_label
from viewer3d.ui.canvas import Canvas
from viewer3d.ui.options import LABEL_MODES, MAX_REPEAT, MIN_REPEAT, STYLES


class DisplayTab(QWidget):
    def __init__(self, canvas: Canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self._syncing = False

        self.style = QComboBox()
        for key, text in STYLES.items():
            self.style.addItem(text, key)
        self.radius = QSlider(Qt.Orientation.Horizontal)
        self.radius.setRange(20, 250)  # 0.20 .. 2.50
        self.radius_text = QLabel()
        self.radius_text.setMinimumWidth(42)
        self.bond_factor = QDoubleSpinBox()
        self.bond_factor.setRange(0.60, 1.80)
        self.bond_factor.setSingleStep(0.01)
        self.bond_factor.setDecimals(2)
        self.show_bonds = QCheckBox("Mostrar ligações")
        self.reps = []
        reps_row = QHBoxLayout()
        for name in "abc":
            spin = QSpinBox()
            spin.setRange(MIN_REPEAT, MAX_REPEAT)
            spin.setPrefix(f"{name} ")
            self.reps.append(spin)
            reps_row.addWidget(spin)
        self.labels = QComboBox()
        for key, text in LABEL_MODES.items():
            self.labels.addItem(text, key)
        self.show_cell = QCheckBox("Caixa da célula")
        self.show_axes = QCheckBox("Eixos (a, b, c e x, y, z)")
        self.perspective = QCheckBox("Projeção em perspectiva")
        self.background = QComboBox()
        self.background.addItem("Escuro", True)
        self.background.addItem("Claro", False)

        form = QFormLayout()
        form.addRow("Estilo:", self.style)
        radius_row = QHBoxLayout()
        radius_row.addWidget(self.radius, 1)
        radius_row.addWidget(self.radius_text)
        form.addRow("Escala do raio:", radius_row)
        form.addRow("Fator de ligação:", self.bond_factor)
        form.addRow(self.show_bonds)
        form.addRow("Repetição:", reps_row)
        form.addRow("Rótulos:", self.labels)
        form.addRow(self.show_cell)
        form.addRow(self.show_axes)
        form.addRow(self.perspective)
        form.addRow("Fundo:", self.background)

        self.species = QTableWidget(0, 3)
        self.species.setHorizontalHeaderLabels(["Cor", "Espécie", "Visível"])
        self.species.verticalHeader().hide()
        self.species.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.species.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.species.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Espécies:"))
        layout.addWidget(self.species, 1)

        self.style.currentIndexChanged.connect(self._changed)
        self.radius.valueChanged.connect(self._changed)
        self.bond_factor.valueChanged.connect(self._changed)
        for widget in (self.show_bonds, self.show_cell, self.show_axes, self.perspective):
            widget.toggled.connect(self._changed)
        for spin in self.reps:
            spin.valueChanged.connect(self._changed)
        self.labels.currentIndexChanged.connect(self._changed)
        self.background.currentIndexChanged.connect(self._changed)
        canvas.options_changed.connect(self.sync)
        self.sync()

    def sync(self) -> None:
        """Widgets <- options (for changes made elsewhere: key P, command line)."""
        o = self.canvas.options
        self._syncing = True
        try:
            self.style.setCurrentIndex(self.style.findData(o.style))
            self.radius.setValue(round(o.radius_scale * 100))
            self.radius_text.setText(f"{o.radius_scale:.2f}×")
            self.bond_factor.setValue(o.bond_factor)
            self.show_bonds.setChecked(o.show_bonds)
            for spin, value in zip(self.reps, o.reps, strict=True):
                spin.setValue(value)
            self.labels.setCurrentIndex(self.labels.findData(o.labels))
            self.show_cell.setChecked(o.show_cell)
            self.show_axes.setChecked(o.show_axes)
            self.perspective.setChecked(o.perspective)
            self.background.setCurrentIndex(self.background.findData(o.dark))
        finally:
            self._syncing = False

    def _changed(self, *_args) -> None:
        if self._syncing:
            return
        o = self.canvas.options
        o.style = self.style.currentData()
        o.radius_scale = self.radius.value() / 100.0
        self.radius_text.setText(f"{o.radius_scale:.2f}×")
        o.bond_factor = round(self.bond_factor.value(), 2)
        o.show_bonds = self.show_bonds.isChecked()
        o.reps = tuple(spin.value() for spin in self.reps)
        o.labels = self.labels.currentData()
        o.show_cell = self.show_cell.isChecked()
        o.show_axes = self.show_axes.isChecked()
        o.perspective = self.perspective.isChecked()
        o.dark = bool(self.background.currentData())
        self.canvas.refresh_options()

    # --- species table ------------------------------------------------------------------
    def structure_changed(self) -> None:
        structure = self.canvas.structure
        self.sync()
        self.species.setRowCount(0)
        if structure is None:
            return
        self.species.setRowCount(len(structure.species))
        for row, spec in enumerate(structure.species):
            element = element_for_label(spec.label)
            button = QPushButton()
            button.setFixedWidth(46)
            button.clicked.connect(lambda _=False, r=row: self._pick_color(r))
            self.species.setCellWidget(row, 0, button)
            self._paint_button(row)
            name = f"{spec.label} ({element.name})" if element.known else spec.label
            label = QLabel(name)
            label.setContentsMargins(6, 0, 0, 0)
            self.species.setCellWidget(row, 1, label)
            box = QCheckBox()
            box.setChecked(row not in self.canvas.options.species_hidden)
            box.toggled.connect(lambda on, r=row: self._set_visible(r, on))
            holder = QWidget()
            inner = QHBoxLayout(holder)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(box)
            self.species.setCellWidget(row, 2, holder)

    def _current_color(self, row: int) -> QColor:
        override = self.canvas.options.species_colors.get(row)
        if override is not None:
            return QColor(*override)
        label = self.canvas.structure.species[row].label
        r, g, b = element_for_label(label).color
        return QColor(round(r * 255), round(g * 255), round(b * 255))

    def _paint_button(self, row: int) -> None:
        color = self._current_color(row)
        button = self.species.cellWidget(row, 0)
        button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #555;")

    def _pick_color(self, row: int) -> None:
        chosen = QColorDialog.getColor(self._current_color(row), self, "Cor da espécie")
        if chosen.isValid():
            self.set_species_color(row, (chosen.red(), chosen.green(), chosen.blue()))

    def set_species_color(self, row: int, rgb: tuple[int, int, int]) -> None:
        self.canvas.options.species_colors[row] = rgb
        self._paint_button(row)
        self.canvas.refresh_options()

    def _set_visible(self, row: int, on: bool) -> None:
        hidden = self.canvas.options.species_hidden
        hidden.discard(row) if on else hidden.add(row)
        self.canvas.refresh_options()
