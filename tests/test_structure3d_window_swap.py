"""Spec 81 R2: a 3D window shows another structure without being made again, picks among several with the
"Estrutura" combo after "Print", and turns "Print" off for a structure not written yet."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from qe_studio.core.structure3d.model import AtomRef
from qe_studio.ui.widgets.structure3d.window import (
    FIXED_TIP,
    NOT_FIXED_TIP,
    PRINT_TIP,
    UNSAVED_TIP,
)
from structure3d_helpers import (
    SI_SCF,
    SLAB_2X1,
    WATER,
    Windows,
    camera_state,
    read_structure,
    same_camera,
    structure_of_text,
    water,
)


@pytest.fixture
def windows(qtbot, tmp_path):
    opened = Windows(qtbot, QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    yield opened
    opened.close_all()


def test_another_structure_in_the_same_window(windows):
    window = windows.open(SI_SCF)
    canvas, panel = window.canvas, window.panel
    canvas.options.radius_scale = 1.6  # a display option of the user's
    assert len(canvas.structure) == 2 and len(panel.swatches) == 1
    window.show_structure(water())
    assert canvas.structure is window.structure and len(canvas.structure) == 3
    assert canvas.scene is not None and len(canvas.scene.positions) == 3
    assert panel.cell_values["nat"].text() == "3" and len(panel.swatches) == 2
    assert panel.atom.structure is window.structure and panel.measures.structure is window.structure
    assert canvas.options.radius_scale == 1.6 and panel.radius.value() == pytest.approx(1.6)
    assert window.windowTitle() == "agua.in · Visualização 3D"
    assert window.info.text().startswith("agua.in · H2O · nat = 3")
    window.canvas.grab()  # a frame of the new scene


def test_the_camera_stays_only_when_asked(windows):
    window = windows.open(structure=water())
    canvas = window.canvas
    canvas.rotate_structure("x")
    turned = camera_state(canvas)
    moved = structure_of_text(WATER.replace("H 6.2517721", "H 6.4517721"))  # same cell
    window.show_structure(moved, keep_camera=True)
    assert same_camera(camera_state(canvas), turned)
    assert canvas.structure.cart[1][0] == pytest.approx(6.4517721)
    window.show_structure(read_structure(SLAB_2X1), keep_camera=False)
    assert not same_camera(camera_state(canvas), turned)  # framed again, isometric


def test_the_current_atom_stays_when_the_atoms_are_the_same(windows):
    window = windows.open(SI_SCF)
    canvas = window.canvas
    canvas.select(AtomRef(1))
    window.show_structure(structure_of_text(SI_SCF.read_text()), keep_camera=True)
    assert canvas.current == AtomRef(1)
    assert window.panel.atom.title.text().startswith("Si2")
    window.panel.measures.set_mode("distancia")
    window.show_structure(water())
    assert canvas.current is None and canvas.marks == ()
    assert window.panel.measures.mode == "distancia" and not window.panel.measures.measurements


def test_species_settings_follow_their_label(windows):
    window = windows.open(structure=water())
    window.panel.set_species_color(1, "#00ff00")  # H
    swapped = WATER.replace("O 15.999 O.UPF\nH 1.008 H.UPF", "H 1.008 H.UPF\nO 15.999 O.UPF")
    window.show_structure(structure_of_text(swapped))  # H is now the first species
    assert window.structure.species[0].label == "H"
    assert window.canvas.options.species_colors == {0: (0, 255, 0)}
    assert window.panel.swatches[0].color == "#00ff00"


def test_the_combo_comes_after_print_with_two_structures(qtbot, windows):
    window = windows.open(SI_SCF)
    combo, bar = window.choice_combo, window.print_button.parentWidget()
    assert combo.isHidden()
    window.set_choices(["SCF base (si.scf.in)", "Slab (vc-relax_si.in)"], 1)
    assert not combo.isHidden() and combo.currentIndex() == 1
    layout = bar.layout()
    assert layout.indexOf(combo) == layout.indexOf(window.print_button) + 1
    assert combo.accessibleName() == "Estrutura"
    with qtbot.waitSignal(window.choice_changed) as blocker:
        combo.setCurrentIndex(0)
        combo.activated.emit(0)
    assert blocker.args == [0]
    window.set_choices(["SCF base (si.scf.in)"], 0)
    assert combo.isHidden()


def test_print_needs_a_file(windows):
    window = windows.open(SI_SCF)
    assert window.print_button.isEnabled() and window.print_button.toolTip() == PRINT_TIP
    unsaved = structure_of_text(WATER)  # no path: an input "Criar" has not written yet
    window.show_structure(unsaved, name="relax_agua.in")
    assert not window.print_button.isEnabled()
    assert window.print_button.toolTip() == UNSAVED_TIP
    assert window.windowTitle() == "relax_agua.in · Visualização 3D"
    assert window.info.text().startswith("relax_agua.in · ")
    window.print_button.click()  # disabled: nothing
    window.show_structure(water())
    assert window.print_button.isEnabled() and window.print_button.toolTip() == PRINT_TIP


def test_a_window_opened_without_a_path(windows):
    window = windows.open(structure=structure_of_text(WATER), name="scf_agua.in")
    assert not window.print_button.isEnabled() and window.print_button.toolTip() == UNSAVED_TIP
    assert window.windowTitle() == "scf_agua.in · Visualização 3D"


def test_the_fixed_atoms_button_is_the_one_of_the_structure_shown(windows):
    """As the preview of "Criar cálculo" swaps them: inputs not written yet, with and without if_pos."""
    window = windows.open(SLAB_2X1)
    button, canvas = window.fixed_button, window.canvas
    window.set_choices(["SCF base (slab.in)", "Relax (relax_agua.in)"], 0)
    button.click()
    dirty = canvas.dirty

    window.show_structure(structure_of_text(WATER), name="scf_agua.in")
    assert not button.isEnabled() and not button.isChecked()
    assert button.toolTip() == NOT_FIXED_TIP
    assert canvas.options.show_fixed is True  # a structure with fixed atoms shows them again

    oxygen = "O 5.2917721 5.2917721 5.2917721"
    fixed = structure_of_text(WATER.replace(oxygen, oxygen + " 0 0 0"))
    window.show_structure(fixed, name="relax_agua.in")
    assert button.isEnabled() and button.isChecked()
    assert button.toolTip() == FIXED_TIP.format(n=1, m=3)
    window.canvas.grab()
    assert canvas.dirty == dirty  # no change of the user's

    window.show_structure(read_structure(SLAB_2X1))
    assert button.isEnabled() and button.isChecked()
    assert button.toolTip() == FIXED_TIP.format(n=28, m=68)
