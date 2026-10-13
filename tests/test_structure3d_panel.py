"""Spec 43 R5: the left panel of the 3D window, with the accordion sections of the plot panel."""

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, QPointF, QSettings, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QSlider,
    QSpinBox,
    QTabWidget,
)

from qe_studio.core.structure3d.model import AtomRef
from qe_studio.ui.widgets.no_wheel import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from qe_studio.ui.widgets.structure3d.panel_atom import PLACEHOLDER
from structure3d_helpers import NI_SCF, SI_SCF, SLAB_2X1, Windows, structure_of_text


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def windows(qtbot, settings):
    opened = Windows(qtbot, settings)
    yield opened
    opened.close_all()


def test_sections_in_order_without_tabs_or_sliders(windows):
    panel = windows.open(SI_SCF).panel
    assert list(panel.sections) == ["Átomo", "Medidas", "Exibição", "Espécies", "Célula"]
    headers = [s.header.text() for s in panel.sections.values()]
    assert headers == ["ÁTOMO", "MEDIDAS", "EXIBIÇÃO", "ESPÉCIES", "CÉLULA"]
    opened = {title: s.header.isChecked() for title, s in panel.sections.items()}
    assert opened == {
        "Átomo": True,
        "Medidas": True,
        "Exibição": True,
        "Espécies": False,
        "Célula": False,
    }
    assert panel.findChildren(QTabWidget) == [] and panel.findChildren(QSlider) == []
    fields = panel.findChildren(QSpinBox) + panel.findChildren(QDoubleSpinBox)
    fields += panel.findChildren(QComboBox)
    assert fields and all(
        isinstance(f, NoWheelSpinBox | NoWheelDoubleSpinBox | NoWheelComboBox) for f in fields
    )
    assert panel.minimumWidth() == 260


def test_the_wheel_does_not_change_a_field(windows):
    panel = windows.open(SI_SCF).panel
    for field in (panel.radius, panel.style_choice, panel.reps[0]):
        before = field.value() if hasattr(field, "value") else field.currentIndex()
        at = QPointF(field.width() / 2, field.height() / 2)
        event = QWheelEvent(
            at,
            field.mapToGlobal(at),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(field, event)
        after = field.value() if hasattr(field, "value") else field.currentIndex()
        assert after == before


def test_an_atom_of_the_slab(windows):
    window = windows.open(SLAB_2X1)
    atom = window.panel.atom
    assert atom.placeholder.text() == PLACEHOLDER and not atom.placeholder.isHidden()
    window.canvas.select(AtomRef(42))
    assert atom.placeholder.isHidden()
    assert atom.title.text() == "O43 · Oxigênio"
    assert atom.value("species") == "O"
    assert atom.value("element") == "Oxigênio (O), Z = 8"
    assert atom.value("mass").endswith(" u")
    assert atom.value("flags") == "1 1 1"  # the slab writes if_pos for some atoms: the row shows
    assert atom.value("image") == ""  # the original copy has no image row
    assert int(atom.value("coordination")) == atom.table.rowCount() > 0
    fixed = next(i for i, f in enumerate(window.structure.flags) if f == (0, 0, 0))
    window.canvas.select(AtomRef(fixed))
    assert atom.title.text() == f"Si{fixed + 1} · Silício"
    assert atom.value("flags") == "0 0 0"
    window.canvas.select(AtomRef(fixed, (1, 0, 0)))
    assert atom.value("image") == "(1, 0, 0)"
    assert atom.title.text() == f"Si{fixed + 1}(1,0,0) · Silício"


def test_silicon_rows_and_neighbours(windows):
    window = windows.open(SI_SCF)
    atom = window.panel.atom
    window.canvas.select(AtomRef(0))
    assert atom.title.text() == "Si1 · Silício"
    assert atom.value("mass") == "28.086 u"
    assert atom.value("pseudo") == "Si.pz-rrkj.UPF"
    assert atom.value("magnetization") == "" and atom.value("flags") == ""  # rows hidden
    assert atom.value("coordination") == "4"
    distances = [atom.table.item(row, 1).text() for row in range(atom.table.rowCount())]
    assert distances == ["2.3300"] * 4  # √3/4 · celldm(1)
    names = [atom.table.item(row, 0).text() for row in range(4)]
    assert all(name.startswith("Si2") for name in names)
    assert atom.more.isHidden()
    neighbour = atom.table.refs[1]
    atom.table.cellClicked.emit(1, 0)
    assert window.canvas.current == neighbour
    assert atom.title.text().startswith(names[1])


def test_starting_magnetization_row(windows):
    window = windows.open(NI_SCF)
    window.canvas.select(AtomRef(0))
    assert window.panel.atom.value("magnetization") == "0.8"


def test_cell_section_matches_the_structure(windows):
    window = windows.open(SI_SCF)
    values = {label: v.text() for label, v in window.panel.cell_values.items()}
    a, b, c, alpha, beta, gamma = window.structure.lattice_parameters
    assert [float(x) for x in values["a, b, c (Å)"].split()] == pytest.approx([a, b, c], abs=1e-5)
    angles = [float(x) for x in values["α, β, γ (°)"].split()]
    assert angles == pytest.approx([alpha, beta, gamma], abs=1e-3)
    assert float(values["Volume (Å³)"]) == pytest.approx(window.structure.volume, abs=1e-4)
    rows = [[float(x) for x in values[f"a{i} (Å)"].split()] for i in "₁₂₃"]
    assert np.allclose(rows, window.structure.cell, atol=1e-4)
    assert (values["ibrav"], values["nat"], values["Fórmula"]) == ("2", "2", "Si2")
    assert (values["prefix"], values["calculation"]) == ("silicon", "scf")
    assert window.panel.warnings == []


def test_reader_warnings_are_lines_of_the_cell_section(windows):
    text = SI_SCF.read_text().replace("Si 0.25", "X 0.25")
    window = windows.open(structure=structure_of_text(text, SI_SCF))
    lines = [label.text() for label in window.panel.warnings]
    assert lines[0].startswith("⚠ Espécie X sem linha em ATOMIC_SPECIES")
    assert lines[1] == "⚠ Espécie sem elemento conhecido: X (cinza, raio 1,0 Å)"
    assert window.warning.isVisibleTo(window) and "Espécie X" in window.warning.toolTip()


def test_sections_remember_open_and_closed(windows):
    window = windows.open(SI_SCF)
    window.panel.sections["Átomo"].header.click()
    window.panel.sections["Célula"].header.click()
    window.close()
    again = windows.open(SI_SCF).panel
    assert not again.sections["Átomo"].header.isChecked()
    assert again.sections["Célula"].header.isChecked()
    assert not again.sections["Átomo"].body.isVisibleTo(again)


def test_bond_factor_follows_the_bonds_box(windows):
    window = windows.open(SI_SCF)
    panel = window.panel
    assert panel.bond_factor.isEnabled()
    panel.show_bonds.setChecked(False)
    assert not panel.bond_factor.isEnabled() and not window.canvas.options.show_bonds
    panel.show_bonds.setChecked(True)
    assert panel.bond_factor.isEnabled()


def test_species_colors_and_restore(windows):
    window = windows.open(SLAB_2X1)
    panel = window.panel
    names = [panel.sections["Espécies"].grid.itemAt(i).widget() for i in range(len(panel.swatches))]
    assert names and all(row is not None for row in names)
    original = panel.swatches[0].color
    panel.swatches[0].color_changed.emit("#00ff00")
    assert panel.swatches[0].color == "#00ff00"
    assert window.canvas.options.species_colors == {0: (0, 255, 0)}
    panel.restore_colors()
    assert panel.swatches[0].color == original and window.canvas.options.species_colors == {}


def test_display_fields_edit_the_options(windows):
    window = windows.open(SI_SCF)
    panel, options = window.panel, window.canvas.options
    panel.labels.setCurrentIndex(panel.labels.findData("indice"))
    assert options.labels == "indice" and panel.labels.currentText() == "Número"
    panel.background.setCurrentIndex(panel.background.findData("claro"))
    assert options.background == "claro"
    panel.radius.setValue(1.25)
    assert options.radius_scale == pytest.approx(1.25)
    assert panel.radius.text() == "1.25×"  # a decimal point
    panel.reps[1].setValue(2)
    assert options.reps == (1, 2, 1)
    window.canvas.grab()
    assert window.canvas.stats.atoms == 4
