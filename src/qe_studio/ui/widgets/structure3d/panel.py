"""The left panel of a 3D window (spec 43 R5): "ESTRUTURA" and the accordion sections of the plot
adjustments panel (``param_widgets.Section``): "Átomo", "Medidas" (spec 44), "Exibição", "Rotação" (spec 46),
"Espécies", "Célula", and under them a fixed footer with "Restaurar padrões" (spec 46 R6).

Every field edits the window's ``DisplayOptions`` and asks the view for a repaint; none moves the camera.
Numeric and choice fields are the ``NoWheel*`` ones (the wheel scrolls the panel). Whether each section is
open is QSettings ``structure3d/sections/<título>``, shared by every window. "Restaurar padrões" makes the
canvas replace its options object: nothing here keeps a reference to it, every use reads
``canvas.options``.
"""

from __future__ import annotations

from PyQt6.QtCore import QLocale, QSettings, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ....core.structure3d.elements import element_for_label
from ....core.structure3d.options import (
    BACKGROUNDS,
    LABEL_MODES,
    MAX_AXIS_WIDTH,
    MAX_FACTOR,
    MAX_LABEL_SIZE,
    MAX_RADIUS,
    MAX_REPEAT,
    MIN_AXIS_WIDTH,
    MIN_FACTOR,
    MIN_LABEL_SIZE,
    MIN_RADIUS,
    MIN_REPEAT,
    STYLES,
    background_of_theme,
)
from ...theme.manager import ThemeManager
from ..common import PanelHeader, set_variant
from ..no_wheel import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from ..param_widgets import ColorButton, Section
from .canvas import StructureCanvas
from .measures import MeasuresSection
from .panel_atom import AtomSection, triple
from .rotation import RotationSection

SECTIONS_KEY = "structure3d/sections"  # QSettings: <section title> → open (bool)
TITLES = ("Átomo", "Medidas", "Exibição", "Rotação", "Espécies", "Célula")
OPEN_BY_DEFAULT = ("Átomo", "Medidas", "Exibição", "Rotação")
MIN_WIDTH = 260
RESTORE_TITLE = "Restaurar padrões"
RESTORE_QUESTION = "Voltar todas as opções e a câmera desta janela ao padrão?"


def ask_restore(parent: QWidget | None) -> bool:
    """The question of "Restaurar padrões", like the plots' (a module function so tests replace it)."""
    answer = QMessageBox.question(
        parent,
        RESTORE_TITLE,
        RESTORE_QUESTION,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def _combo(choices: dict[str, str]) -> NoWheelComboBox:
    combo = NoWheelComboBox()
    for key, text in choices.items():
        combo.addItem(text, key)
    return combo


def _decimal(low: float, high: float, step: float, suffix: str = "") -> NoWheelDoubleSpinBox:
    spin = NoWheelDoubleSpinBox()
    spin.setLocale(QLocale.c())  # a decimal point, like the rest of the interface
    spin.setRange(low, high)
    spin.setSingleStep(step)
    spin.setDecimals(2)
    spin.setSuffix(suffix)
    return spin


def _hex(rgb: tuple[int, int, int]) -> str:
    return QColor(*rgb).name()


class StructurePanel(QWidget):
    def __init__(
        self,
        theme: ThemeManager,
        canvas: StructureCanvas,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("structurePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(MIN_WIDTH)
        self.theme, self.canvas, self.settings = theme, canvas, settings
        self.structure = canvas.structure
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(PanelHeader(theme, "Estrutura", "bubble_chart"))
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("structureScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("structureBody")
        self.column = QVBoxLayout(body)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(0)
        self.sections: dict[str, Section] = {title: self._section(title) for title in TITLES}
        self.column.addStretch(1)
        self.scroll_area.setWidget(body)
        layout.addWidget(self.scroll_area, 1)
        self.restore_button = QPushButton(RESTORE_TITLE)
        self.restore_button.setObjectName("structureRestore")
        self.restore_button.setToolTip("Voltar as opções, a câmera e a rotação ao padrão")
        self.restore_button.clicked.connect(self._restore_clicked)
        footer = QWidget()
        footer.setObjectName("structureFooter")
        line = QHBoxLayout(footer)
        line.setContentsMargins(8, 6, 8, 6)
        line.addWidget(self.restore_button)
        layout.addWidget(footer)

        self.atom = AtomSection(self.sections["Átomo"], self.structure)
        self.atom.show_atom(canvas.current, canvas.graph)
        self.atom.table.neighbor_clicked.connect(canvas.select)
        self.measures = MeasuresSection(self.sections["Medidas"], canvas)
        self._build_display(self.sections["Exibição"])
        self.rotation = RotationSection(self.sections["Rotação"], canvas)
        self._build_species(self.sections["Espécies"])
        self._build_cell(self.sections["Célula"])
        canvas.current_changed.connect(self._current_changed)
        canvas.options_changed.connect(self.sync)
        self.sync()

    # -- sections ----------------------------------------------------------------------------------
    def _section(self, title: str) -> Section:
        key = f"{SECTIONS_KEY}/{title}"
        opened = title in OPEN_BY_DEFAULT
        if self.settings is not None:
            opened = bool(self.settings.value(key, opened, type=bool))
        section = Section(self.theme, title, opened)
        section.opened_changed.connect(lambda on, k=key: self._remember_open(k, on))
        self.column.addWidget(section)
        return section

    def _remember_open(self, key: str, opened: bool) -> None:
        if self.settings is not None:
            self.settings.setValue(key, opened)

    def _current_changed(self, ref) -> None:
        self.atom.show_atom(ref, self.canvas.graph)

    # -- Exibição ----------------------------------------------------------------------------------
    def _build_display(self, section: Section) -> None:
        self.style_choice = _combo(STYLES)
        self.radius = _decimal(MIN_RADIUS, MAX_RADIUS, 0.05, "×")
        self.bond_factor = _decimal(MIN_FACTOR, MAX_FACTOR, 0.05)
        self.reps: list[NoWheelSpinBox] = []
        reps = QWidget()
        row = QHBoxLayout(reps)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for name in "abc":
            spin = NoWheelSpinBox()
            spin.setRange(MIN_REPEAT, MAX_REPEAT)
            spin.setPrefix(f"{name} ")
            spin.setAccessibleName(f"Repetição ao longo de {name}")
            self.reps.append(spin)
            row.addWidget(spin)
        self.labels = _combo(LABEL_MODES)
        self.label_size = NoWheelSpinBox()
        self.label_size.setRange(MIN_LABEL_SIZE, MAX_LABEL_SIZE)
        self.label_size.setSuffix(" px")
        self.background = _combo(BACKGROUNDS)
        self.show_bonds, self.show_cell, self.perspective = QCheckBox(), QCheckBox(), QCheckBox()
        self.show_xyz, self.show_abc = QCheckBox(), QCheckBox()
        self.xyz_width = _decimal(MIN_AXIS_WIDTH, MAX_AXIS_WIDTH, 0.5, " px")
        self.abc_width = _decimal(MIN_AXIS_WIDTH, MAX_AXIS_WIDTH, 0.5, " px")
        section.add_row("Estilo", self.style_choice)
        section.add_row("Raio", self.radius, "Escala do raio dos átomos")
        section.add_row("Fator de ligação", self.bond_factor, "Ligação: d < fator × (r₁ + r₂)")
        section.add_row("Repetição", reps)
        section.add_row("Rótulos", self.labels)
        section.add_row(
            "Tamanho dos rótulos",
            self.label_size,
            "Tamanho do texto da vista: rótulos dos átomos e nomes dos eixos",
        )
        section.add_row("Fundo", self.background)
        # the check boxes together, one after the other (spec 46 R2.3), then the widths they enable
        section.add_row("Ligações", self.show_bonds)
        section.add_row("Caixa da célula", self.show_cell)
        section.add_row("Perspectiva", self.perspective)
        section.add_row("Eixos x, y, z", self.show_xyz, "Triedro x, y, z do canto da vista")
        section.add_row("Eixos a, b, c", self.show_abc, "Setas a, b, c da célula")
        section.add_row("Espessura x, y, z", self.xyz_width, "Espessura do triedro x, y, z")
        section.add_row("Espessura a, b, c", self.abc_width, "Espessura das setas a, b, c")

        for combo in (self.style_choice, self.labels, self.background):
            combo.currentIndexChanged.connect(self._changed)
        for spin in (self.radius, self.bond_factor, *self.reps, self.label_size):
            spin.valueChanged.connect(self._changed)
        for spin in (self.xyz_width, self.abc_width):
            spin.valueChanged.connect(self._changed)
        for box in (
            self.show_bonds,
            self.show_cell,
            self.perspective,
            self.show_xyz,
            self.show_abc,
        ):
            box.toggled.connect(self._changed)

    def sync(self) -> None:
        """Widgets ← options (after a change made in the view: the P key, "Restaurar padrões")."""
        o = self.canvas.options
        self._syncing = True
        try:
            self.style_choice.setCurrentIndex(self.style_choice.findData(o.style))
            self.radius.setValue(o.radius_scale)
            self.show_bonds.setChecked(o.show_bonds)
            self.bond_factor.setValue(o.bond_factor)
            self.bond_factor.setEnabled(o.show_bonds)
            for spin, value in zip(self.reps, o.reps, strict=True):
                spin.setValue(value)
            self.labels.setCurrentIndex(self.labels.findData(o.labels))
            self.label_size.setValue(o.label_size)
            self.show_cell.setChecked(o.show_cell)
            self.show_xyz.setChecked(o.show_xyz)
            self.show_abc.setChecked(o.show_abc)
            self.xyz_width.setValue(o.xyz_width)
            self.abc_width.setValue(o.abc_width)
            self.xyz_width.setEnabled(o.show_xyz)
            self.abc_width.setEnabled(o.show_abc)
            self.perspective.setChecked(o.perspective)
            self.background.setCurrentIndex(self.background.findData(o.background))
            self._sync_species()
        finally:
            self._syncing = False

    def _changed(self, *_args) -> None:
        if self._syncing:
            return
        o = self.canvas.options
        o.style = self.style_choice.currentData()
        o.radius_scale = round(self.radius.value(), 2)
        o.show_bonds = self.show_bonds.isChecked()
        o.bond_factor = round(self.bond_factor.value(), 2)
        o.reps = (self.reps[0].value(), self.reps[1].value(), self.reps[2].value())
        o.labels = self.labels.currentData()
        o.label_size = self.label_size.value()
        o.show_cell = self.show_cell.isChecked()
        o.show_xyz = self.show_xyz.isChecked()
        o.show_abc = self.show_abc.isChecked()
        o.xyz_width = round(self.xyz_width.value(), 2)
        o.abc_width = round(self.abc_width.value(), 2)
        o.perspective = self.perspective.isChecked()
        o.background = self.background.currentData()
        self.bond_factor.setEnabled(o.show_bonds)
        self.xyz_width.setEnabled(o.show_xyz)
        self.abc_width.setEnabled(o.show_abc)
        self.canvas.refresh_options()

    def _restore_clicked(self) -> None:
        """ "Restaurar padrões": ask, then the options and the camera go back to a new window's, with
        the background of the app theme *now*."""
        if ask_restore(self):
            self.canvas.restore_defaults(background_of_theme(self.theme.name))

    # -- Espécies ----------------------------------------------------------------------------------
    def _build_species(self, section: Section) -> None:
        self.swatches: list[ColorButton] = []
        self.visible: list[QCheckBox] = []
        for index, species in enumerate(self.structure.species):
            element = element_for_label(species.label)
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            swatch = ColorButton(self._color_of(index))
            swatch.color_changed.connect(lambda color, i=index: self.set_species_color(i, color))
            name = f"{species.label} · {element.name}" if element.known else species.label
            box = QCheckBox("Visível")
            box.setChecked(index not in self.canvas.options.species_hidden)
            box.setAccessibleName(f"{species.label} visível")
            box.toggled.connect(lambda on, i=index: self.set_species_visible(i, on))
            line.addWidget(swatch)
            line.addWidget(QLabel(name), 1)
            line.addWidget(box)
            section.add_full(row)
            self.swatches.append(swatch)
            self.visible.append(box)
        restore = QPushButton("Restaurar cores")
        restore.clicked.connect(self.restore_colors)
        section.add_full(restore)

    def _color_of(self, index: int) -> str:
        override = self.canvas.options.species_colors.get(index)
        return _hex(override if override is not None else self.canvas.renderer.species_rgb(index))

    def set_species_color(self, index: int, color: str) -> None:
        rgb = QColor(color)
        self.canvas.options.species_colors[index] = (rgb.red(), rgb.green(), rgb.blue())
        self.swatches[index].set_color(color)
        self.canvas.refresh_options()

    def set_species_visible(self, index: int, on: bool) -> None:
        hidden = self.canvas.options.species_hidden
        if on:
            hidden.discard(index)
        else:
            hidden.add(index)
        self.canvas.refresh_options()

    def restore_colors(self) -> None:
        self.canvas.options.species_colors.clear()
        self._sync_species()
        self.canvas.refresh_options()

    def _sync_species(self) -> None:
        """Swatches and "Visível" boxes ← options, without a ``set_species_*`` per row."""
        options = self.canvas.options
        for index, swatch in enumerate(self.swatches):
            swatch.set_color(self._color_of(index))
        for index, box in enumerate(self.visible):
            box.blockSignals(True)
            box.setChecked(index not in options.species_hidden)
            box.blockSignals(False)

    # -- Célula ------------------------------------------------------------------------------------
    def _build_cell(self, section: Section) -> None:
        structure, source = self.structure, self.structure.source
        a, b, c, alpha, beta, gamma = structure.lattice_parameters
        rows = [
            ("a, b, c (Å)", triple((a, b, c), 5), True),
            ("α, β, γ (°)", triple((alpha, beta, gamma), 3), True),
            ("Volume (Å³)", f"{structure.volume:.4f}", True),
            ("a₁ (Å)", triple(structure.cell[0], 4), True),
            ("a₂ (Å)", triple(structure.cell[1], 4), True),
            ("a₃ (Å)", triple(structure.cell[2], 4), True),
            ("ibrav", str(source.ibrav), False),
            ("nat", str(source.nat), False),
            ("Fórmula", structure.formula, False),
            ("prefix", source.prefix, False),
            ("calculation", source.calculation, False),
        ]
        self.cell_values: dict[str, QLabel] = {}
        for label, text, mono in rows:
            value = set_variant(QLabel(text), "readout") if mono else QLabel(text)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            section.add_row(label, value)
            self.cell_values[label] = value
        self.warnings: list[QLabel] = []
        for warning in source.warnings:
            line = set_variant(QLabel(f"⚠ {warning}"), "warning")
            line.setWordWrap(True)
            section.add_full(line)
            self.warnings.append(line)
