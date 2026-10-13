"""Spec 43 R3: the camera moves only by a gesture; clicks, a double click and every field of the panel
keep the zoom, the pan and the rotation the user made."""

import numpy as np
import pytest
from PyQt6.QtCore import QSettings, Qt

from qe_studio.core.structure3d.model import AtomRef
from structure3d_helpers import (
    LEFT,
    SI_SCF,
    SLAB_2X1,
    Windows,
    camera_state,
    click_atom,
    clickable_atom,
    empty_spot,
    move_to,
    same_camera,
    screen_of,
    zoom_pan_turn,
)


@pytest.fixture
def windows(qtbot, tmp_path):
    opened = Windows(qtbot, QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    yield opened
    opened.close_all()


@pytest.fixture(params=[SI_SCF, SLAB_2X1], ids=["si", "slab"])
def view(request, qtbot, windows):
    """A window whose view the user zoomed, moved and turned; ``initial`` is the view it opened with."""
    window = windows.open(request.param)
    window.initial = camera_state(window.canvas)
    zoom_pan_turn(qtbot, window.canvas)
    return window


def test_the_gestures_move_the_camera(view):
    zoom, pan, rotation = camera_state(view.canvas)
    initial_zoom, initial_pan, initial_rotation = view.initial
    assert zoom > initial_zoom * 1.5
    assert not np.allclose(pan, initial_pan)
    assert not np.allclose(rotation, initial_rotation)


def click(qtbot, window):
    click_atom(qtbot, window.canvas, clickable_atom(window.canvas))


def double_click(qtbot, window):
    """What the platform sends for a double click: press, release, double click, release (QTest's
    ``mouseDClick`` sends only the double click event)."""
    canvas = window.canvas
    ref = clickable_atom(canvas)
    at = screen_of(canvas, ref)
    qtbot.mouseClick(canvas, LEFT, pos=at)
    qtbot.mouseDClick(canvas, LEFT, pos=at)
    qtbot.mouseRelease(canvas, LEFT, pos=at)
    assert canvas.current == ref  # a double click is two clicks: the atom stays selected


def empty_click(qtbot, window):
    click(qtbot, window)
    qtbot.mouseClick(window.canvas, LEFT, pos=empty_spot(window.canvas))
    assert window.canvas.current is None


def ctrl_click(qtbot, window):
    canvas = window.canvas
    ref = clickable_atom(canvas)
    click_atom(qtbot, canvas, ref, Qt.KeyboardModifier.ControlModifier)
    assert canvas.current == ref


def neighbour_click(qtbot, window):
    click(qtbot, window)
    table = window.panel.atom.table
    assert table.rowCount() > 0
    neighbour = table.refs[0]
    qtbot.mouseClick(table.viewport(), LEFT, pos=table.visualItemRect(table.item(0, 0)).center())
    assert window.canvas.current == neighbour


def bond_factor(qtbot, window):
    window.panel.bond_factor.setValue(1.40)
    assert window.canvas.options.bond_factor == pytest.approx(1.40)


def style(qtbot, window):
    window.panel.style_choice.setCurrentIndex(window.panel.style_choice.findData("vareta"))


def radius(qtbot, window):
    window.panel.radius.setValue(1.6)


def color(qtbot, window):
    window.panel.swatches[0].color_changed.emit("#123456")
    assert window.canvas.options.species_colors[0] == (0x12, 0x34, 0x56)


def visibility(qtbot, window):
    window.panel.visible[0].setChecked(False)
    assert 0 in window.canvas.options.species_hidden


@pytest.mark.parametrize(
    "action",
    [
        click,
        double_click,
        empty_click,
        ctrl_click,
        neighbour_click,
        bond_factor,
        style,
        radius,
        color,
        visibility,
    ],
)
def test_the_camera_stays(qtbot, view, action):
    before = camera_state(view.canvas)
    action(qtbot, view)
    view.canvas.repaint()
    assert same_camera(camera_state(view.canvas), before)


def test_r_and_the_button_restore_the_initial_view(qtbot, view):
    qtbot.keyClick(view.canvas, Qt.Key.Key_R)
    assert same_camera(camera_state(view.canvas), view.initial)
    zoom_pan_turn(qtbot, view.canvas)
    view.reset_button.click()
    assert same_camera(camera_state(view.canvas), view.initial)


def test_a_new_repetition_frames_the_block_keeping_the_rotation(view):
    zoom, _pan, rotation = camera_state(view.canvas)
    view.panel.reps[0].setValue(3)
    new_zoom, _new_pan, new_rotation = camera_state(view.canvas)
    assert new_zoom != pytest.approx(zoom)
    assert np.allclose(new_rotation, rotation)


def test_keys_and_view_menu(qtbot, windows):
    window = windows.open(SI_SCF)
    canvas = window.canvas
    assert canvas.options.perspective and window.panel.perspective.isChecked()
    qtbot.keyClick(canvas, Qt.Key.Key_P)
    assert not canvas.options.perspective and not window.panel.perspective.isChecked()
    qtbot.keyClick(canvas, Qt.Key.Key_C)
    c = canvas.structure.cell[2]
    assert canvas.camera.rotation[2] @ c == pytest.approx(np.linalg.norm(c))
    window.view_actions["x"].trigger()
    assert np.allclose(canvas.camera.rotation[2], [1, 0, 0])
    zoom = canvas.camera.zoom
    qtbot.keyClick(canvas, Qt.Key.Key_Plus)
    assert canvas.camera.zoom > zoom


def test_hover_names_the_atom_in_the_status_bar(qtbot, windows):
    window = windows.open(SLAB_2X1)
    canvas = window.canvas
    ref = clickable_atom(canvas)
    with qtbot.waitSignal(canvas.hovered, timeout=2000):
        move_to(canvas, screen_of(canvas, ref))
    name = window.hover.text()
    assert name.startswith(f"{canvas.structure.symbols[ref.index]}{ref.index + 1} · ")
    move_to(canvas, empty_spot(canvas))
    assert window.hover.text() == ""


def test_a_click_selects_and_the_ring_follows(qtbot, windows):
    window = windows.open(SI_SCF)
    canvas = window.canvas
    ref = clickable_atom(canvas)
    click_atom(qtbot, canvas, ref)
    assert canvas.current == ref
    canvas.select(AtomRef(0, (1, 0, 0)))  # a copy outside the drawn block still gets its ring
    assert canvas.current == AtomRef(0, (1, 0, 0))
    canvas.repaint()


def test_focus_draws_the_focus_ring(qtbot, windows):
    window = windows.open(SI_SCF)
    canvas = window.canvas
    canvas.setFocus()
    qtbot.waitUntil(canvas.hasFocus)
    image = canvas.grab().toImage()
    ring = window.canvas.theme.color("focus_ring")
    assert image.pixelColor(0, canvas.height() // 2).name() == ring.name()
