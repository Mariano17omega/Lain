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


def kinds(measures) -> list[str]:
    return [m.kind for m in measures.measurements]


def table_items(measures) -> list:
    """The measures the tables hold, distances then angles (each table in its row order)."""
    return [*measures.tables["distancia"].items, *measures.tables["angulo"].items]


def test_apagar_removes_the_last_measure_made_of_either_kind(qtbot, window):
    """Spec 46 R4: d1, d2, a1 made in this order go a1, d2, d1."""
    measures, canvas = window.panel.measures, window.canvas
    a, b, c = clickable_atoms(canvas, 3)
    assert not measures.delete_button.isEnabled()
    assert measures.delete_button.text() == "Apagar"
    assert measures.delete_button.toolTip() == "Apagar a última medida"
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b, b, c])  # d1 = a-b, d2 = b-c
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b, c])  # a1
    assert kinds(measures) == ["distancia", "distancia", "angulo"]
    assert measures.delete_button.isEnabled()
    d1, d2, a1 = measures.measurements

    measures.delete_button.click()
    assert measures.measurements == [d1, d2]
    assert measures.tables["angulo"].isHidden() and measures.captions["angulo"].isHidden()
    assert measures.tables["distancia"].items == [d1, d2]
    measures.delete_button.click()
    assert measures.measurements == [d1] and measures.tables["distancia"].items == [d1]
    assert len(measures.tables["distancia"].texts()) == 1
    measures.delete_button.click()
    assert measures.measurements == []
    assert all(t.rowCount() == 0 and t.isHidden() for t in measures.tables.values())
    assert not measures.delete_button.isEnabled()
    assert not measures.copy_button.isEnabled() and not measures.clear_button.isEnabled()
    measures.delete_last()  # nothing to remove: no error
    assert measures.measurements == []


def test_apagar_takes_the_last_made_and_not_the_selected_row(qtbot, window):
    measures = window.panel.measures
    a, b, c = clickable_atoms(window.canvas, 3)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b, b, c])
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b, c])
    d1, d2, a1 = measures.measurements

    measures.tables["distancia"].selectRow(0)  # d1 selected: not the one that goes
    measures.delete_button.click()
    assert measures.measurements == [d1, d2]
    measures.tables["distancia"].selectRow(0)
    measures.delete_button.click()  # the last made is d2, d1 stays selected or not
    assert measures.measurements == [d1] and measures.tables["distancia"].items == [d1]


def test_apagar_keeps_the_atoms_of_a_measure_under_way(qtbot, window):
    measures, canvas = window.panel.measures, window.canvas
    a, b, c = clickable_atoms(canvas, 3)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b])  # d1
    clicks(qtbot, window, [c])  # one atom of the next, pending
    assert measures.measurer.pending == (c,) and len(measures.measurements) == 1

    measures.delete_button.click()
    assert measures.measurements == []  # the previous measure went
    assert measures.measurer.pending == (c,)  # the one under way is still there
    assert canvas.marks == (c,)
    assert measures.mode == "distancia" and "Selecionados" in measures.hint.text()
    clicks(qtbot, window, [a])  # and it completes: c-a
    assert len(measures.measurements) == 1
    assert [r for r in measures.measurements[0].refs] == [c, a]


def test_copy_after_apagar_does_not_carry_the_measure(qtbot, window):
    measures, structure = window.panel.measures, window.structure
    a, b, c = clickable_atoms(window.canvas, 3)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b, b, c])
    measures.delete_button.click()
    measures.copy_button.click()
    text = QApplication.clipboard().text()
    assert text == to_tsv(structure, measures.measurements)
    assert text.count("\n") == 2  # the header and the one measure left
    assert row_text(structure, measures.measurements[0])[0] in text


def test_measures_and_table_rows_agree_after_mixing_delete_and_apagar(qtbot, window):
    measures = window.panel.measures
    a, b, c = clickable_atoms(window.canvas, 3)
    measures.buttons["distancia"].click()
    clicks(qtbot, window, [a, b, b, c, a, c])  # d1 d2 d3
    measures.buttons["angulo"].click()
    clicks(qtbot, window, [a, b, c, b, c, a])  # a1 a2
    table = measures.tables["distancia"]
    table.selectRow(0)
    table.setFocus()
    qtbot.keyClick(table, Qt.Key.Key_Delete)  # d1 goes by Delete
    measures.delete_button.click()  # a2 goes by Apagar
    assert kinds(measures) == ["distancia", "distancia", "angulo"]
    assert sorted(id(m) for m in measures.measurements) == sorted(
        id(m) for m in table_items(measures)
    )
    for mode, tab in measures.tables.items():
        assert tab.rowCount() == len(tab.items) == len(tab.texts())
        assert [m.kind for m in tab.items] == [mode] * len(tab.items)
    measures.delete_button.click()  # a1
    measures.delete_button.click()  # d3
    assert kinds(measures) == ["distancia"]
    assert measures.tables["angulo"].isHidden()
    assert [m for m in measures.tables["distancia"].items] == measures.measurements


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
