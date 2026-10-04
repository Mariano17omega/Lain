"""Spec 26 R4.3: the band path table of "Criar cálculo"."""

import pytest

from qe_studio.core.calc_create.kpath import KPath, KPathUnavailable, KPoint, to_card
from qe_studio.ui.widgets.kpath_editor import K1, LABEL, NPTS, KPathEditor

from calc_helpers import AL_PATH

FOLDED = KPath(AL_PATH.points[:2], warnings=("as bandas aparecem dobradas",))


@pytest.fixture
def editor(qtbot):
    widget = KPathEditor(suggest=lambda: AL_PATH)
    qtbot.addWidget(widget)
    return widget


def labels(editor: KPathEditor) -> list[str]:
    return [point.label for point in editor.value().points]


def suggested(qtbot, editor: KPathEditor, action) -> None:
    with qtbot.waitSignal(editor.changed, timeout=5000):
        action()
    qtbot.waitUntil(lambda: editor.suggest_button.isEnabled())


def test_empty_editor_is_an_empty_path(editor):
    assert editor.value() == KPath(())
    assert not editor.remove_button.isEnabled()


def test_first_visit_fills_an_empty_table(qtbot, editor):
    changes = []
    editor.changed.connect(changes.append)
    suggested(qtbot, editor, editor.ensure_suggested)
    assert editor.value() == AL_PATH
    assert changes == [False]  # a suggestion is not a user edit
    assert editor.table.item(4, NPTS).text() == "—"
    editor.ensure_suggested()  # only the first visit asks
    assert not editor._running


def test_first_visit_keeps_what_was_typed(qtbot):
    editor = KPathEditor(suggest=lambda: AL_PATH)
    qtbot.addWidget(editor)
    editor.add_point()
    editor.ensure_suggested()  # the table is not empty: no suggestion
    assert not editor._running
    assert len(editor.value().points) == 1


def test_suggest_button_replaces(qtbot, editor):
    editor.add_point()
    editor.add_point()
    changes = []
    editor.changed.connect(changes.append)
    suggested(qtbot, editor, editor.suggest_button.click)
    assert editor.value() == AL_PATH
    assert changes[-1] is True


def test_suggestion_warnings_are_shown(qtbot):
    editor = KPathEditor(suggest=lambda: FOLDED)
    qtbot.addWidget(editor)
    suggested(qtbot, editor, editor.ensure_suggested)
    assert editor.notes == ("as bandas aparecem dobradas",)
    assert editor.message.text() == "as bandas aparecem dobradas"


def test_unavailable_leaves_the_table_empty(qtbot):
    def unavailable() -> KPath:
        raise KPathUnavailable("pymatgen não está instalado: digite os pontos do caminho")

    editor = KPathEditor(suggest=unavailable)
    qtbot.addWidget(editor)
    suggested(qtbot, editor, editor.ensure_suggested)
    assert editor.table.rowCount() == 0
    assert editor.notes == (
        "Sem sugestão de caminho: pymatgen não está instalado: digite os pontos do caminho",
    )
    assert not editor.message.isHidden()


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


def test_card_of_the_edited_path(editor):
    editor.set_path(AL_PATH)
    assert to_card(editor.value()) == to_card(AL_PATH)


def test_no_suggestion_without_a_suggest(qtbot):
    editor = KPathEditor()
    qtbot.addWidget(editor)
    editor.ensure_suggested()
    assert editor.suggest_button.isHidden()
    assert not editor._running
