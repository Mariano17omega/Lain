"""Spec 46 R3: the "Rotação" section of the 3D window: six buttons that turn the structure 45° about
the Cartesian x, y and z axes, through the center of the view, without framing it again."""

import numpy as np
import pytest
from PyQt6.QtCore import QSettings

from structure3d_helpers import (
    SI_SCF,
    SLAB_2X1,
    Windows,
    camera_state,
    click_atom,
    clickable_atom,
    clickable_atoms,
    same_camera,
)

NAMES = ["x+", "y+", "z+", "x-", "y-", "z-"]


@pytest.fixture
def windows(qtbot, tmp_path):
    opened = Windows(qtbot, QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    yield opened
    opened.close_all()


def about(axis: str, degrees: float) -> np.ndarray:
    """The right-hand rotation matrix about a world axis, written out."""
    t = np.radians(degrees)
    c, s = np.cos(t), np.sin(t)
    return {
        "x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
        "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
        "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]),
    }[axis]


def test_the_section_comes_after_exibicao_and_is_open(windows):
    panel = windows.open(SI_SCF).panel
    titles = list(panel.sections)
    assert titles.index("Rotação") == titles.index("Exibição") + 1
    section = panel.sections["Rotação"]
    assert section.header.text() == "ROTAÇÃO" and section.header.isChecked()
    assert section.body.isVisibleTo(panel)


def test_six_buttons_in_a_grid_with_their_tips(windows):
    rotation = windows.open(SI_SCF).panel.rotation
    assert list(rotation.buttons) == NAMES
    for name, button in rotation.buttons.items():
        assert button.text() == name
        tip = button.toolTip()
        assert tip.startswith("Girar a estrutura 45° em torno de " + name[0])
        assert tip.endswith("(regra da mão direita)" if name[1] == "+" else "no sentido contrário")
        assert button.accessibleName() == tip
    grid = rotation.buttons["x+"].parent().layout()
    for name, button in rotation.buttons.items():
        row, column, _, _ = grid.getItemPosition(grid.indexOf(button))
        assert (row, column) == (0 if name[1] == "+" else 1, "xyz".index(name[0]))


@pytest.mark.parametrize("name", NAMES)
def test_a_click_turns_the_structure_45_degrees_about_the_axis(windows, name):
    window = windows.open(SLAB_2X1)
    canvas = window.canvas
    ref = clickable_atom(canvas)
    click_atom(windows.qtbot, canvas, ref)  # a current atom
    rotation, (zoom, pan, _) = canvas.camera.rotation.copy(), camera_state(canvas)
    center = canvas.camera.center.copy()

    window.panel.rotation.buttons[name].click()
    canvas.grab()

    axis, sign = name[0], 1.0 if name[1] == "+" else -1.0
    assert np.allclose(canvas.camera.rotation, rotation @ about(axis, sign * 45.0), atol=1e-12)
    assert canvas.camera.zoom == zoom and np.array_equal(canvas.camera.pan, pan)
    assert np.array_equal(canvas.camera.center, center)
    assert canvas.current == ref


def test_an_atom_off_the_axis_moves_on_the_screen(windows):
    window = windows.open(SLAB_2X1)
    canvas = window.canvas
    atom = next(a for a in clickable_atoms(canvas, 4))
    position = canvas.renderer.screen_position(atom)
    window.panel.rotation.buttons["z+"].click()
    canvas.grab()
    moved = canvas.renderer.screen_position(atom)
    assert moved is not None and np.hypot(moved[0] - position[0], moved[1] - position[1]) > 1.0


def test_the_center_of_the_block_does_not_move_on_the_screen(windows):
    canvas = windows.open(SLAB_2X1).canvas
    size = (float(canvas.width()), float(canvas.height()))
    before, _, _ = canvas.camera.project(canvas.camera.center[None, :], size)
    window = canvas.window()
    for name in ("x+", "y-", "z+", "z+"):
        window.panel.rotation.buttons[name].click()
    after, _, _ = canvas.camera.project(canvas.camera.center[None, :], size)
    assert np.allclose(before, after)


def test_rotating_never_measures_selects_or_marks(qtbot, windows):
    window = windows.open(SLAB_2X1)
    panel, canvas = window.panel, window.canvas
    a, b = clickable_atoms(canvas, 2)
    panel.measures.buttons["distancia"].click()
    click_atom(qtbot, canvas, a)  # one atom pending
    pending, marks, current = panel.measures.measurer.pending, canvas.marks, canvas.current
    assert pending == (a,) and marks == (a,)

    for name in NAMES:
        panel.rotation.buttons[name].click()
    assert panel.measures.measurer.pending == pending and canvas.marks == marks
    assert canvas.current == current and panel.measures.measurements == []
    assert panel.measures.mode == "distancia"
    click_atom(qtbot, canvas, b)  # the measure under way still completes
    assert len(panel.measures.measurements) == 1


@pytest.mark.parametrize("perspective", [True, False], ids=["perspectiva", "ortografica"])
def test_perspective_and_orthographic_turn_alike(windows, perspective):
    window = windows.open(SI_SCF)
    canvas = window.canvas
    window.panel.perspective.setChecked(perspective)
    start = canvas.camera.rotation.copy()
    window.panel.rotation.buttons["y+"].click()
    window.panel.rotation.buttons["z-"].click()
    expected = start @ about("y", 45.0) @ about("z", -45.0)
    assert np.allclose(canvas.camera.rotation, expected, atol=1e-12)


def test_eight_clicks_close_a_turn_and_the_view_is_not_framed_again(windows):
    window = windows.open(SLAB_2X1)
    canvas = window.canvas
    window.panel.reps[0].setValue(2)  # the block changes size: framed again, by itself
    canvas.grab()
    start = camera_state(canvas)
    for _ in range(8):
        window.panel.rotation.buttons["x+"].click()
    canvas.grab()
    assert same_camera(camera_state(canvas), start)
    window.panel.rotation.buttons["z+"].click()
    canvas.grab()
    assert canvas.camera.zoom == start[0]  # no framing: the zoom of the user stays
