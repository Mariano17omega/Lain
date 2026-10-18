"""Spec 43 R5: the left panel of the 3D window, with the accordion sections of the plot panel."""

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, QPointF, QSettings, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QSlider,
    QSpinBox,
    QTabWidget,
)

from qe_studio.core.structure3d.model import AtomRef
from qe_studio.core.structure3d.options import DisplayOptions
from qe_studio.ui.widgets.no_wheel import NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from qe_studio.ui.widgets.structure3d.panel_atom import PLACEHOLDER
from structure3d_helpers import (
    NI_SCF,
    SI_SCF,
    SLAB_2X1,
    Windows,
    camera_state,
    click_atom,
    clickable_atoms,
    same_camera,
    structure_of_text,
    zoom_pan_turn,
)

PANEL = "qe_studio.ui.widgets.structure3d.panel"


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
    assert list(panel.sections) == ["atom", "measures", "display", "rotation", "species", "cell"]
    headers = [s.header.text() for s in panel.sections.values()]
    assert headers == ["ÁTOMO", "MEDIDAS", "EXIBIÇÃO", "ROTAÇÃO", "ESPÉCIES", "CÉLULA"]
    opened = {title: s.header.isChecked() for title, s in panel.sections.items()}
    assert opened == {
        "atom": True,
        "measures": True,
        "display": True,
        "rotation": True,
        "species": False,
        "cell": False,
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
    numeric = (panel.label_size, panel.xyz_width, panel.abc_width)
    for field in (panel.radius, panel.style_choice, panel.reps[0], *numeric):
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
    assert [float(x) for x in values["abc"].split()] == pytest.approx([a, b, c], abs=1e-5)
    angles = [float(x) for x in values["angles"].split()]
    assert angles == pytest.approx([alpha, beta, gamma], abs=1e-3)
    assert float(values["volume"]) == pytest.approx(window.structure.volume, abs=1e-4)
    rows = [[float(x) for x in values[f"a{i}"].split()] for i in "123"]
    assert np.allclose(rows, window.structure.cell, atol=1e-4)
    assert (values["ibrav"], values["nat"], values["formula"]) == ("2", "2", "Si2")
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
    window.panel.sections["atom"].header.click()
    window.panel.sections["cell"].header.click()
    window.close()
    again = windows.open(SI_SCF).panel
    assert not again.sections["atom"].header.isChecked()
    assert again.sections["cell"].header.isChecked()
    assert not again.sections["atom"].body.isVisibleTo(again)


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
    names = [panel.sections["species"].grid.itemAt(i).widget() for i in range(len(panel.swatches))]
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


# -- spec 46 R2: the rows of "Exibição", two axis boxes, widths and the label size -------------------

DISPLAY_ROWS = [
    "Estilo",
    "Raio",
    "Fator de ligação",
    "Repetição",
    "Rótulos",
    "Tamanho dos rótulos",
    "Fundo",
    "Ligações",
    "Caixa da célula",
    "Perspectiva",
    "Eixos x, y, z",
    "Eixos a, b, c",
    "Espessura x, y, z",
    "Espessura a, b, c",
]


def test_the_display_rows_are_in_order_and_the_check_boxes_are_together(windows):
    grid = windows.open(SI_SCF).panel.sections["display"].grid
    rows = [row for row in range(grid.rowCount()) if grid.itemAtPosition(row, 0) is not None]
    labels = [grid.itemAtPosition(row, 0).widget().text() for row in rows]
    assert labels == DISPLAY_ROWS
    boxes = [row for row in rows if isinstance(grid.itemAtPosition(row, 1).widget(), QCheckBox)]
    assert len(boxes) == 5
    assert boxes == list(range(boxes[0], boxes[0] + 5))  # consecutive rows of the grid
    names = [grid.itemAtPosition(row, 0).widget().text() for row in boxes]
    assert names == ["Ligações", "Caixa da célula", "Perspectiva", "Eixos x, y, z", "Eixos a, b, c"]


def test_each_axes_box_edits_only_its_option_and_enables_its_width(windows):
    window = windows.open(SI_SCF)
    panel, options = window.panel, window.canvas.options
    assert panel.show_xyz.isChecked() and panel.show_abc.isChecked()
    assert panel.xyz_width.isEnabled() and panel.abc_width.isEnabled()
    assert not hasattr(panel, "show_axes")

    panel.show_xyz.setChecked(False)
    assert (options.show_xyz, options.show_abc) == (False, True)
    assert not panel.xyz_width.isEnabled() and panel.abc_width.isEnabled()
    panel.show_xyz.setChecked(True)
    panel.show_abc.setChecked(False)
    assert (options.show_xyz, options.show_abc) == (True, False)
    assert panel.xyz_width.isEnabled() and not panel.abc_width.isEnabled()
    panel.show_abc.setChecked(True)
    assert panel.abc_width.isEnabled()


def test_the_new_fields_edit_their_option_and_sync_brings_them_back(qtbot, windows):
    window = windows.open(SI_SCF)
    panel, canvas = window.panel, window.canvas
    options = canvas.options
    assert (options.label_size, options.xyz_width, options.abc_width) == (11, 2.0, 1.8)
    assert panel.label_size.value() == 11 and panel.label_size.suffix() == " px"
    assert (panel.label_size.minimum(), panel.label_size.maximum()) == (8, 32)
    assert (panel.xyz_width.minimum(), panel.xyz_width.maximum()) == (0.5, 8.0)
    assert panel.xyz_width.singleStep() == 0.5 and panel.abc_width.suffix() == " px"
    assert panel.xyz_width.text() == "2.00 px"  # a decimal point

    panel.label_size.setValue(20)
    panel.xyz_width.setValue(4.5)
    panel.abc_width.setValue(3.0)
    assert (options.label_size, options.xyz_width, options.abc_width) == (20, 4.5, 3.0)

    # changed from the view (the P key sends ``options_changed``): the panel follows
    options.label_size, options.xyz_width, options.abc_width = 14, 1.0, 7.5
    options.show_xyz = options.show_abc = False
    qtbot.keyClick(canvas, Qt.Key.Key_P)
    assert panel.label_size.value() == 14
    assert (panel.xyz_width.value(), panel.abc_width.value()) == (1.0, 7.5)
    assert not panel.show_xyz.isChecked() and not panel.show_abc.isChecked()
    assert not panel.xyz_width.isEnabled() and not panel.abc_width.isEnabled()


def test_no_field_of_the_display_moves_the_camera(windows):
    window = windows.open(SI_SCF)
    panel = window.panel
    before = camera_state(window.canvas)
    panel.label_size.setValue(24)
    panel.xyz_width.setValue(5.0)
    panel.abc_width.setValue(0.5)
    panel.show_abc.setChecked(False)
    panel.show_xyz.setChecked(False)
    window.canvas.grab()
    assert same_camera(camera_state(window.canvas), before)


# -- spec 46 R6: "Restaurar padrões" -----------------------------------------------------------------


def restore_answer(monkeypatch, answer: bool) -> list:
    asked: list = []
    monkeypatch.setattr(f"{PANEL}.ask_restore", lambda parent: asked.append(parent) or answer)
    return asked


def change_everything(qtbot, window) -> None:
    panel, canvas = window.panel, window.canvas
    panel.style_choice.setCurrentIndex(panel.style_choice.findData("fio"))
    panel.radius.setValue(1.6)
    panel.reps[0].setValue(2)
    panel.labels.setCurrentIndex(panel.labels.findData("ambos"))
    panel.label_size.setValue(18)
    panel.show_xyz.setChecked(False)
    panel.show_abc.setChecked(False)
    panel.xyz_width.setValue(5.0)
    panel.abc_width.setValue(4.0)
    panel.perspective.setChecked(False)
    panel.background.setCurrentIndex(panel.background.findData("claro"))
    panel.swatches[0].color_changed.emit("#00ff00")
    panel.visible[1].setChecked(False)
    zoom_pan_turn(qtbot, canvas)
    canvas.rotate_structure("z")


def test_restore_defaults_goes_back_to_a_new_windows_options_and_camera(
    qtbot, windows, monkeypatch
):
    window = windows.open(SLAB_2X1)
    panel, canvas = window.panel, window.canvas
    original_colors = [swatch.color for swatch in panel.swatches]
    initial = camera_state(canvas)
    old_options = canvas.options
    asked = restore_answer(monkeypatch, True)
    change_everything(qtbot, window)
    assert canvas.options.species_colors and canvas.options.species_hidden
    assert not same_camera(camera_state(canvas), initial)
    assert not canvas.restored

    panel.restore_button.click()

    assert asked == [panel]
    assert canvas.options == DisplayOptions(background="escuro")
    assert canvas.options is not old_options and canvas.restored
    assert panel.style_choice.currentData() == "bola-vareta" and panel.radius.value() == 1.0
    assert [spin.value() for spin in panel.reps] == [1, 1, 1]
    assert panel.labels.currentData() == "nenhum" and panel.label_size.value() == 11
    assert panel.show_xyz.isChecked() and panel.show_abc.isChecked()
    assert (panel.xyz_width.value(), panel.abc_width.value()) == (2.0, 1.8)
    assert panel.xyz_width.isEnabled() and panel.abc_width.isEnabled()
    assert panel.perspective.isChecked() and panel.show_bonds.isChecked()
    assert panel.background.currentData() == "escuro"
    assert [swatch.color for swatch in panel.swatches] == original_colors
    assert all(box.isChecked() for box in panel.visible)
    canvas.grab()
    assert same_camera(camera_state(canvas), initial)


def test_restore_defaults_asks_and_a_no_changes_nothing(qtbot, windows, monkeypatch):
    window = windows.open(SLAB_2X1)
    panel, canvas = window.panel, window.canvas
    restore_answer(monkeypatch, False)
    change_everything(qtbot, window)
    options, camera = canvas.options, camera_state(canvas)
    before = (options.radius_scale, options.species_hidden.copy(), options.label_size)
    panel.restore_button.click()
    assert canvas.options is options and not canvas.restored
    assert (options.radius_scale, options.species_hidden, options.label_size) == before
    assert same_camera(camera_state(canvas), camera)
    assert panel.radius.value() == 1.6 and not panel.visible[1].isChecked()


def test_restore_defaults_keeps_the_current_atom_and_the_measures(qtbot, windows, monkeypatch):
    window = windows.open(SLAB_2X1)
    panel, canvas = window.panel, window.canvas
    first, second = clickable_atoms(canvas, 2)
    panel.measures.buttons["distancia"].click()
    click_atom(qtbot, canvas, first)
    click_atom(qtbot, canvas, second)
    assert len(panel.measures.measurements) == 1 and canvas.current == second
    restore_answer(monkeypatch, True)
    panel.radius.setValue(1.7)
    panel.restore_button.click()
    assert canvas.options.radius_scale == 1.0
    assert canvas.current == second and len(panel.measures.measurements) == 1
    assert panel.measures.mode == "distancia"
    assert panel.sections["display"].header.isChecked()  # the sections keep their state


def test_restore_defaults_takes_the_background_of_the_theme_now(windows, monkeypatch):
    windows.theme.set_mode("light")
    window = windows.open(SI_SCF)
    assert window.canvas.options.background == "claro"
    restore_answer(monkeypatch, True)
    window.panel.background.setCurrentIndex(window.panel.background.findData("escuro"))
    window.panel.restore_button.click()
    assert window.canvas.options == DisplayOptions(background="claro")
    # the theme changes while the window is open: the next restore follows the app, not the opening
    windows.theme.set_mode("dark")
    window.panel.restore_button.click()
    assert window.canvas.options.background == "escuro"
    assert window.panel.background.currentData() == "escuro"


def test_the_panel_follows_the_new_options_object_after_a_restore(windows, monkeypatch):
    window = windows.open(SI_SCF)
    panel, canvas = window.panel, window.canvas
    restore_answer(monkeypatch, True)
    panel.restore_button.click()
    options = canvas.options
    panel.radius.setValue(1.9)
    panel.show_abc.setChecked(False)
    assert canvas.options is options  # edited in place, the new object
    assert options.radius_scale == 1.9 and not options.show_abc
    window.canvas.rotate_structure("x")  # the buttons work on the restored view
    assert panel.rotation.buttons["x+"].isEnabled()
    species = panel.visible[0]
    species.setChecked(False)
    assert options.species_hidden == {0}


def test_the_restore_button_is_a_fixed_footer_below_the_scroll(windows):
    panel = windows.open(SI_SCF).panel
    assert panel.restore_button.text() == "Restaurar padrões"
    assert panel.restore_button.isEnabled()
    assert "padrão" in panel.restore_button.toolTip()
    assert not panel.scroll_area.isAncestorOf(panel.restore_button)  # always in view
    assert panel.restore_button.parent().parent() is panel
