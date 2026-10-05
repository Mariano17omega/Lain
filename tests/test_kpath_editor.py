"""Spec 26 R4.3 and spec 27-2: the band path table of "Criar cálculo" (typed, never suggested)."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from qe_studio.core.calc_create.kpath import MAX_NPTS, KPath, KPoint, distribute, to_card
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.kpath_editor import BREAK_TIP, K1, LABEL, NPTS, KPathEditor

from calc_helpers import AL_PATH, al, hex_cell, hex_path


@pytest.fixture
def theme(qtbot):
    return ThemeManager("dark")


@pytest.fixture
def editor(qtbot, theme):
    widget = KPathEditor(theme, al().crystal.cell)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def hex_editor(qtbot, theme):
    widget = KPathEditor(theme, hex_cell())
    qtbot.addWidget(widget)
    return widget


def labels(editor: KPathEditor) -> list[str]:
    return [point.label for point in editor.value().points]


def marked(editor: KPathEditor) -> list[int]:
    """The rows drawn in the warning color."""
    return [
        row
        for row in range(editor.table.rowCount())
        if editor.table.item(row, LABEL).foreground().style() != Qt.BrushStyle.NoBrush
    ]


def test_empty_editor_is_an_empty_path(editor):
    assert editor.value() == KPath(())
    assert editor.table.rowCount() == 0
    assert not editor.remove_button.isEnabled()


def test_there_is_no_suggestion(editor):
    texts = [button.text() for button in editor.findChildren(QPushButton)]
    assert not any("Sugerir" in text or "pymatgen" in text for text in texts)
    assert "Distribuir pelo comprimento" in texts
    assert not hasattr(editor, "ensure_suggested")


def test_add_remove_and_reorder(editor):
    editor.set_path(AL_PATH)
    editor.table.setCurrentCell(1, LABEL)
    editor.move_point(1)
    assert labels(editor) == ["L", "X", "Gamma", "U", "Gamma"]
    assert editor.table.currentRow() == 2
    editor.move_point(-1)
    editor.move_point(-1)
    assert labels(editor) == ["Gamma", "L", "X", "U", "Gamma"]
    editor.remove_point()
    assert labels(editor) == ["L", "X", "U", "Gamma"]
    editor.table.setCurrentCell(3, LABEL)
    editor.add_point()
    assert labels(editor) == ["L", "X", "U", "Gamma", ""]
    assert editor.value().points[-1] == KPoint("", (0.0, 0.0, 0.0), 20)
    assert not editor.down_button.isEnabled()  # the new point is last and selected


def test_set_path_is_not_a_user_edit(editor):
    changes = []
    editor.changed.connect(changes.append)
    editor.set_path(AL_PATH)
    assert editor.value() == AL_PATH
    assert changes == [False]
    assert editor.table.item(4, NPTS).text() == "—"


def test_break_makes_the_path_jump(editor):
    editor.set_path(AL_PATH)
    editor.table.setCurrentCell(2, LABEL)
    editor.toggle_break()
    path = editor.value()
    assert path.breaks == frozenset({2})
    assert path.weights() == [20, 30, 1, 30, 1]
    assert editor.table.item(2, NPTS).text() == "quebra"
    editor.move_point(1)  # the jump travels with its point
    assert editor.value().breaks == frozenset({3})
    editor.toggle_break()
    assert editor.value().breaks == frozenset()
    assert editor.table.item(3, NPTS).text() == "10"  # X keeps its own count
    editor.table.setCurrentCell(4, LABEL)
    assert not editor.break_button.isEnabled()  # nothing after the last point


def test_a_point_added_after_a_break_takes_the_break_with_it(editor):
    """L G X|U G: the break stays between the new point and U, the pair the user had broken."""
    editor.set_path(AL_PATH)
    editor.table.setCurrentCell(2, LABEL)
    editor.toggle_break()
    editor.add_point()
    assert labels(editor) == ["L", "Gamma", "X", "", "U", "Gamma"]
    assert editor.value().breaks == frozenset({3})
    assert editor.table.item(2, NPTS).text() == "10"  # X is a plain point again, its own count
    editor.table.setCurrentCell(0, LABEL)
    editor.add_point()  # after a point with no break: nothing moves
    assert editor.value().breaks == frozenset({4})


def test_removing_a_point_with_a_break_passes_the_break_back(editor):
    editor.set_path(AL_PATH)
    editor.table.setCurrentCell(2, LABEL)
    editor.toggle_break()
    editor.remove_point()  # X|U goes: Gamma|U
    assert labels(editor) == ["L", "Gamma", "U", "Gamma"]
    assert editor.value().breaks == frozenset({1})
    editor.table.setCurrentCell(0, LABEL)
    editor.toggle_break()
    editor.remove_point()  # the first point has no one before it: the break goes with it
    assert editor.value().breaks == frozenset({0})  # Gamma|U is still there, now at index 0
    editor.table.setCurrentCell(1, LABEL)
    editor.remove_point()  # U goes, nothing breaks: Gamma|Gamma
    assert labels(editor) == ["Gamma", "Gamma"] and editor.value().breaks == frozenset({0})
    editor.table.setCurrentCell(1, LABEL)
    editor.remove_point()  # the Gamma left is the last point: a break after it means nothing
    assert editor.value().breaks == frozenset()


def test_typed_numbers(editor):
    editor.set_path(AL_PATH)
    changes = []
    editor.changed.connect(changes.append)
    editor.table.item(0, K1).setText("0,25")
    assert editor.value().points[0].frac == (0.25, 0.5, 0.0)
    assert editor.table.item(0, K1).text() == "0.25"
    editor.table.item(0, K1).setText("meio")
    assert editor.value().points[0].frac[0] == 0.25  # back to the last valid value
    assert editor.message.text() == "Valor inválido: meio"
    editor.table.item(0, NPTS).setText("0")
    assert editor.value().points[0].npts == 20
    editor.table.item(0, NPTS).setText("40")
    assert editor.value().weights()[0] == 40
    editor.table.item(0, LABEL).setText(" W ")
    assert labels(editor)[0] == "W"
    assert changes == [True] * 5


@pytest.mark.parametrize("text", ["nan", "inf", "-inf", "1e999", "-1e999", "1_0", "infinity"])
def test_cells_refuse_what_is_not_a_finite_number(editor, text):
    editor.set_path(AL_PATH)
    editor.table.item(0, K1).setText(text)
    assert editor.value().points[0].frac[0] == 0.0  # back to the last valid value
    assert editor.table.item(0, K1).text() == "0"
    assert editor.message.text() == f"Valor inválido: {text}"
    editor.table.item(0, K1).setText("0.5")
    assert editor.message.isHidden()


@pytest.mark.parametrize("text", ["0", "-3", "1001", "20.5", "1_0", "nan", "inf", "1e3", ""])
def test_points_are_an_integer_from_1_to_the_maximum(editor, text):
    editor.set_path(AL_PATH)
    editor.table.item(0, NPTS).setText(text)
    assert editor.value().points[0].npts == 20
    assert editor.message.text().startswith("Valor inválido")


def test_points_limits_are_accepted(editor):
    editor.set_path(AL_PATH)
    editor.table.item(0, NPTS).setText(str(MAX_NPTS))
    editor.table.item(1, NPTS).setText("1")
    assert [p.npts for p in editor.value().points[:2]] == [MAX_NPTS, 1]
    assert editor.message.isHidden()


def test_card_of_the_edited_path(editor):
    editor.set_path(AL_PATH)
    assert to_card(editor.value()) == to_card(AL_PATH)


def test_the_collapsing_segment_is_marked_and_the_mark_follows_the_edits(hex_editor, theme):
    hex_editor.set_path(hex_path())
    assert marked(hex_editor) == [4]  # A→L
    cell = hex_editor.table.item(4, LABEL)
    assert cell.foreground().color() == theme.color("warning")
    assert cell.toolTip().startswith("Segmento A→L colapsa no eixo x do bands.x")
    assert hex_editor.table.item(4, NPTS).toolTip() == cell.toolTip()
    hex_editor.table.item(4, NPTS).setText("150")  # the step shrinks to the one before it
    assert marked(hex_editor) == []
    assert hex_editor.table.item(4, NPTS).toolTip() == ""
    hex_editor.table.item(4, NPTS).setText("20")
    assert marked(hex_editor) == [4]


def test_marks_do_not_count_as_edits_nor_hide_the_break_tip(hex_editor):
    changes = []
    hex_editor.changed.connect(changes.append)
    hex_editor.set_path(hex_path())
    hex_editor.refresh_marks()
    assert changes == [False]
    hex_editor.table.setCurrentCell(1, LABEL)
    hex_editor.toggle_break()
    assert changes == [False, True]
    assert hex_editor.table.item(1, NPTS).toolTip() == BREAK_TIP
    assert hex_editor.table.item(4, LABEL).toolTip().startswith("Segmento A→L")


def test_the_mark_follows_the_theme(hex_editor, theme):
    hex_editor.set_path(hex_path())
    theme.set_mode("light")
    assert hex_editor.table.item(4, LABEL).foreground().color() == theme.color("warning")


def test_no_marks_without_a_cell(qtbot, theme):
    editor = KPathEditor(theme)
    qtbot.addWidget(editor)
    editor.set_path(hex_path())
    assert marked(editor) == []


def test_distribute_changes_only_the_points_column(hex_editor):
    hex_editor.set_path(hex_path())
    before = hex_editor.value()
    changes = []
    hex_editor.changed.connect(changes.append)
    hex_editor.table.setCurrentCell(1, LABEL)
    hex_editor.toggle_break()
    hex_editor.table.setCurrentCell(1, LABEL)
    hex_editor.toggle_break()  # on, off: the same path as before
    hex_editor.distribute_button.click()
    after = hex_editor.value()
    assert changes[-1] is True
    assert after == distribute(before, hex_cell(), 25)
    assert after != before
    assert [(p.label, p.frac) for p in after.points] == [(p.label, p.frac) for p in before.points]
    assert after.breaks == before.breaks
    assert marked(hex_editor) == []


def test_distribute_uses_the_density_field(hex_editor):
    hex_editor.set_path(hex_path())
    assert hex_editor.density.value() == 25
    hex_editor.density.setValue(10)
    hex_editor.distribute_button.click()
    assert hex_editor.value() == distribute(hex_path(), hex_cell(), 10)


def test_distribute_never_runs_by_itself(hex_editor):
    hex_editor.set_path(hex_path())
    hex_editor.add_point()
    hex_editor.table.item(0, NPTS).setText("33")
    assert hex_editor.value().points[0].npts == 33
    assert hex_editor.value().points[1].npts == 20


def test_distribute_button_needs_a_cell_and_two_points(qtbot, theme, editor):
    assert not editor.distribute_button.isEnabled()  # no points
    editor.add_point()
    assert not editor.distribute_button.isEnabled()  # one
    editor.add_point()
    assert editor.distribute_button.isEnabled()
    assert "comprimento" in editor.distribute_button.toolTip()
    unreadable = KPathEditor(theme)
    qtbot.addWidget(unreadable)
    unreadable.set_path(AL_PATH)
    assert not unreadable.distribute_button.isEnabled()
    assert unreadable.distribute_button.toolTip() == "Estrutura do SCF não legível"
    unreadable.distribute_by_length()  # a click that cannot happen does nothing
    assert unreadable.value() == AL_PATH
