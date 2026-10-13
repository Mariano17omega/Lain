"""Spec 44 R2: the "Medidas" section of the 3D window: two exclusive modes, one row per pair or trio in
click order, Copiar / Limpar / Delete, numbered atoms on the view, and the camera left alone."""

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication

from qe_studio.core.structure3d.measure import angle, distance
from qe_studio.core.structure3d.measurements import Measurement, row_text, to_tsv
from qe_studio.ui.widgets.structure3d.overlay import HIGHLIGHT
from structure3d_helpers import (
    LEFT,
    SLAB_2X1,
    Windows,
    camera_state,
    click_atom,
    clickable_atoms,
    empty_spot,
    same_camera,
)


@pytest.fixture
def windows(qtbot, tmp_path):
    opened = Windows(qtbot, QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    yield opened
    opened.close_all()


@pytest.fixture
def window(windows):
    return windows.open(SLAB_2X1)


def clicks(qtbot, window, refs) -> None:
    for ref in refs:
        click_atom(qtbot, window.canvas, ref)


def test_the_requested_sequence_of_distances(qtbot, window):
    measures, structure = window.panel.measures, window.structure
    a, b, c = clickable_atoms(window.canvas, 3)
    window.panel.measures.buttons["distancia"].click()
    assert measures.mode == "distancia"
    clicks(qtbot, window, [a, b, a, c, b, c])
    expected = [
        row_text(structure, Measurement("distancia", pair, distance(structure, *pair)))
        for pair in ((a, b), (a, c), (b, c))
    ]
    assert measures.tables["distancia"].texts() == expected
    assert expected[0][1].endswith(" Å") and expected[0][0].count(" - ") == 1
    assert measures.tables["distancia"].selected_rows() == [2]  # the newest row
    assert measures.tables["angulo"].isHidden() and measures.captions["angulo"].isHidden()
    assert not measures.tables["distancia"].isHidden()


def test_two_trios_make_two_angles(qtbot, window):
    measures, structure = window.panel.measures, window.structure
    a, b, c, d = clickable_atoms(window.canvas, 4)
    measures.buttons["angulo"].click()
    assert measures.hint.text() == "Clique em três átomos; o segundo é o vértice."
    clicks(qtbot, window, [a, b, c, a, b, d])
    rows = measures.tables["angulo"].texts()
    assert len(rows) == 2
    assert rows[0][1] == f"{angle(structure, a, b, c):.2f}°"
    assert rows[1][1] == f"{angle(structure, a, b, d):.2f}°"
    assert measures.tables["distancia"].isHidden()


def test_without_a_mode_a_click_measures_nothing(qtbot, window):
    measures = window.panel.measures
    a, b = clickable_atoms(window.canvas, 2)
    assert measures.mode is None
    assert measures.hint.text() == "Escolha Distância ou Ângulos para medir."
    clicks(qtbot, window, [a, b])
    assert measures.measurements == [] and window.canvas.marks == ()
    assert window.canvas.current == b  # "Átomo" still shows the click
    assert not measures.copy_button.isEnabled() and not measures.clear_button.isEnabled()


def test_the_buttons_are_exclusive_and_may_both_be_off(window):
    buttons = window.panel.measures.buttons
    assert not buttons["distancia"].isChecked() and not buttons["angulo"].isChecked()
    buttons["distancia"].click()
    buttons["angulo"].click()
    assert buttons["angulo"].isChecked() and not buttons["distancia"].isChecked()
    assert window.panel.measures.mode == "angulo"
    buttons["angulo"].click()
    assert not buttons["angulo"].isChecked() and window.panel.measures.mode is None


def test_pending_atoms_are_numbered_and_dropped(qtbot, window):
    measures, canvas = window.panel.measures, window.canvas
    a, b, c = clickable_atoms(canvas, 3)
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b])
    assert canvas.marks == (a, b) and measures.measurer.pending == (a, b)
    assert measures.hint.text().startswith("Selecionados: ") and " → " in measures.hint.text()
    measures.buttons["distancia"].click()  # changing the mode drops them
    assert measures.measurer.pending == () and canvas.marks == ()
    click_atom(qtbot, canvas, a)
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert measures.measurer.pending == () and canvas.marks == ()
    click_atom(qtbot, canvas, a)
    qtbot.mouseClick(canvas, LEFT, pos=empty_spot(canvas))
    assert measures.measurer.pending == () and canvas.marks == ()
    clicks(qtbot, window, [a, c])
    assert canvas.marks == (a, c)  # the measure just made stays numbered
    click_atom(qtbot, canvas, b)
    assert canvas.marks == (b,)
    assert len(measures.measurements) == 1
    canvas.grab()  # the numbered rings are drawn


def test_a_selected_row_numbers_its_atoms(qtbot, window):
    measures, canvas = window.panel.measures, window.canvas
    a, b, c = clickable_atoms(canvas, 3)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b, a, c])
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b, c])
    measures.tables["distancia"].selectRow(0)
    assert canvas.marks == (a, b)
    assert measures.tables["angulo"].selected_rows() == []


def test_copy_clear_and_delete(qtbot, window):
    measures, structure = window.panel.measures, window.structure
    a, b, c = clickable_atoms(window.canvas, 3)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b, b, c])
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b, c])
    assert measures.copy_button.isEnabled()
    measures.copy_button.click()
    assert QApplication.clipboard().text() == to_tsv(structure, measures.measurements)
    assert QApplication.clipboard().text().startswith("Medida\tÁtomos\tValor\nDistância\t")
    assert window.statusBar().currentMessage() == "Medidas copiadas"

    table = measures.tables["distancia"]
    table.selectRow(0)
    table.setFocus()
    qtbot.keyClick(table, Qt.Key.Key_Delete)
    assert len(table.texts()) == 1 and len(measures.measurements) == 2
    assert [m.kind for m in measures.measurements] == ["distancia", "angulo"]

    measures.clear_button.click()
    assert measures.measurements == []
    assert all(t.rowCount() == 0 and t.isHidden() for t in measures.tables.values())
    assert not measures.copy_button.isEnabled() and window.canvas.marks == ()


def test_measuring_leaves_the_camera_alone(qtbot, window):
    measures, canvas = window.panel.measures, window.canvas
    a, b, c = clickable_atoms(canvas, 3)
    before = camera_state(canvas)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b])
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b, c])
    measures.tables["distancia"].selectRow(0)
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    measures.clear_button.click()
    canvas.grab()
    assert same_camera(camera_state(canvas), before)


def test_each_window_has_its_own_measures(qtbot, windows):
    first, second = windows.open(SLAB_2X1), windows.open(SLAB_2X1)
    a, b = clickable_atoms(first.canvas, 2)
    first.panel.measures.buttons["distancia"].click()
    clicks(qtbot, first, [a, b])
    assert len(first.panel.measures.measurements) == 1
    assert second.panel.measures.measurements == [] and second.panel.measures.mode is None


def highlighted(canvas) -> int:
    """Pixels of the rings' color on the view (the numbered marks and the current atom's ring)."""
    from test_structure3d_render import pixels

    image = pixels(canvas.render_image(canvas.size()))
    return int((image == HIGHLIGHT).all(axis=-1).sum())


def test_the_marks_are_drawn(qtbot, window):
    canvas = window.canvas
    a, b = clickable_atoms(canvas, 2)
    assert highlighted(canvas) == 0
    canvas.set_marks((a, b))
    assert highlighted(canvas) > 50
    canvas.set_marks(())
    assert highlighted(canvas) == 0
