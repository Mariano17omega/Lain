"""Spec 30 R3.2: the table of atoms the PDOS window and the charge-difference tab share."""

import pytest

from qe_studio.ui.widgets.plot.atom_table import AtomRow, AtomTable

ROWS = [
    AtomRow(3, "O", "0.5", "0.5", "0.25"),
    AtomRow(1, "Al", "0", "0", "0"),
    AtomRow(2, "Al", "1.5", "0", "0"),
    AtomRow(4, "O", "-0.5", "0.5", "0.75"),
]


@pytest.fixture
def table(qtbot):
    widget = AtomTable(ROWS, (2,), "alat")
    qtbot.addWidget(widget)
    return widget


def test_rows_in_atom_order_with_the_text_given(table):
    assert [table.table.item(r, 1).text() for r in range(4)] == ["1", "2", "3", "4"]
    assert [table.table.item(2, c).text() for c in range(2, 6)] == ["O", "0.5", "0.5", "0.25"]
    assert table.headers() == ("", "#", "Elemento", "x (alat)", "y (alat)", "z (alat)")
    assert [table.table.horizontalHeaderItem(c).text() for c in range(6)] == list(table.headers())


def test_selected_is_the_start_and_none_is_all(qtbot, table):
    assert table.value() == (2,) and table.count.text() == "1 de 4 átomos"
    everything = AtomTable(ROWS, None)
    qtbot.addWidget(everything)
    assert everything.value() == (1, 2, 3, 4)
    nothing = AtomTable(ROWS, ())
    qtbot.addWidget(nothing)
    assert nothing.value() == () and nothing.count.text() == "0 de 4 átomos"
    assert nothing.headers()[3] == "x (Å)"  # the unit defaults to Å


def test_the_count_format_is_the_callers(qtbot):
    widget = AtomTable(ROWS, [1, 2], count_format="{n} de {m} marcados")
    qtbot.addWidget(widget)
    assert widget.count.text() == "2 de 4 marcados"


def test_a_click_changes_the_mark_and_says_so_once(qtbot, table):
    with qtbot.waitSignal(table.changed, timeout=1000):
        table.checks[3].click()
    assert table.checked() == [2, 3] and table.count.text() == "2 de 4 átomos"


def test_a_button_says_it_once_however_many_marks_it_flips(qtbot, table):
    heard = []
    table.changed.connect(lambda: heard.append(table.value()))
    table.mark_all.click()
    table.unmark_all.click()
    table.checks[1].setChecked(True)
    table.invert.click()
    assert heard == [(1, 2, 3, 4), (), (1,), (2, 3, 4)]  # one call per action, never per check
    table.species_menu.actions()[1].trigger()  # O
    assert heard[-1] == (3, 4) and table.value() == (3, 4)
    assert [a.text() for a in table.species_menu.actions()] == ["Al", "O"]


def test_the_species_menu_keeps_the_order_of_the_atoms(qtbot):
    widget = AtomTable([AtomRow(1, "O", "0", "0", "0"), AtomRow(2, "Al", "0", "0", "0")], ())
    qtbot.addWidget(widget)
    assert [a.text() for a in widget.species_menu.actions()] == ["O", "Al"]


def test_no_rows_is_an_empty_table(qtbot):
    widget = AtomTable([], ())
    qtbot.addWidget(widget)
    assert widget.table.rowCount() == 0 and widget.value() == ()
    assert widget.count.text() == "0 de 0 átomos"
    widget.mark_all.click()  # nothing to mark, nothing raised
    assert widget.value() == ()


NOTED = [
    AtomRow(41, "O", "0.1", "0.2", "0.5", "A (4) · H 0,97"),
    AtomRow(45, "O", "0.3", "0.4", "0.5", "B (4) · H 0,97"),
]


def test_the_site_column_shows_only_with_notes(qtbot, table):
    assert table.table.columnCount() == 6 and "Sítio" not in table.headers()
    noted = AtomTable(NOTED, (), "crystal")
    qtbot.addWidget(noted)
    assert noted.headers()[-1] == "Sítio" and noted.table.columnCount() == 7
    assert noted.table.item(1, 6).text() == "B (4) · H 0,97"
    assert noted.headers()[3] == "x (crystal)"


def test_set_rows_keeps_the_marks_still_listed(qtbot, table):
    heard = []
    table.changed.connect(lambda: heard.append(table.value()))
    table.checks[3].click()  # 2 and 3 marked
    heard.clear()
    moved = table.set_rows([AtomRow(3, "O", "0", "0", "0"), AtomRow(5, "H", "1", "1", "1")])
    assert moved and heard == [(3,)]  # 2 left the list: one change
    assert table.value() == (3,) and table.count.text() == "1 de 2 átomos"
    assert [a.text() for a in table.species_menu.actions()] == ["O", "H"]
    assert not table.set_rows([AtomRow(3, "O", "0", "0", "0", "A (2)")])  # same marks: silent
    assert heard == [(3,)] and table.table.columnCount() == 7
    table.checks[3].click()  # the new checks are wired
    assert heard[-1] == ()


def test_the_columns_are_titled_by_the_caller(qtbot):
    """Spec 76 R1.3: the checkbox and note columns take the caller's titles."""
    fixed = AtomTable(NOTED, (41,), "crystal", check_header="Fixo", note_header="if_pos no SCF")
    qtbot.addWidget(fixed)
    assert fixed.headers()[0] == "Fixo" and fixed.headers()[-1] == "if_pos no SCF"
    assert fixed.table.horizontalHeaderItem(0).text() == "Fixo"
    assert fixed.table.horizontalHeaderItem(6).text() == "if_pos no SCF"


def test_set_rows_with_marks_replaces_them(qtbot, table):
    """Spec 76 R1.1: the marks given win over the user's; one change, or none when they are the same."""
    heard = []
    table.changed.connect(lambda: heard.append(table.value()))
    table.checks[3].click()  # 2 and 3 marked
    heard.clear()
    assert table.set_rows(ROWS, (1, 4)) and heard == [(1, 4)]
    assert table.count.text() == "2 de 4 átomos"
    assert not table.set_rows(ROWS, [4, 1]) and heard == [(1, 4)]
    assert table.set_rows(ROWS, ()) and table.value() == ()


# -- the filter of the "Sítio" tab (spec 87 R5) ----------------------------------------------------
@pytest.fixture
def filtered(qtbot):
    widget = AtomTable(ROWS, (2,), "alat", species_filter=True)
    qtbot.addWidget(widget)
    return widget


def hidden(table: AtomTable) -> list[int]:
    return [row.index for number, row in enumerate(table.rows) if table.table.isRowHidden(number)]


def pick_species(table: AtomTable, name: str) -> None:
    next(a for a in table.species_menu.actions() if a.text() == name).trigger()


def test_the_filter_hides_rows_and_keeps_the_marks(filtered):
    heard = []
    filtered.changed.connect(lambda: heard.append(filtered.value()))
    assert [a.text() for a in filtered.species_menu.actions()] == ["Todas", "Al", "O"]
    assert hidden(filtered) == [] and filtered.species_button.text() == "Só espécie ▸"
    assert filtered.species_button.toolTip().startswith("Mostrar só os átomos")
    pick_species(filtered, "O")
    assert hidden(filtered) == [1, 2] and filtered.value() == (2,)
    assert filtered.species_button.text() == "Só espécie: O ▸"
    pick_species(filtered, "Al")
    assert hidden(filtered) == [3, 4] and filtered.species_button.text() == "Só espécie: Al ▸"
    pick_species(filtered, "Todas")
    assert hidden(filtered) == [] and filtered.species_button.text() == "Só espécie ▸"
    assert filtered.value() == (2,) and heard == []  # no mark moved: nothing to plan again


def test_the_count_says_what_the_filter_hides(filtered):
    assert filtered.count.text() == "1 de 4 átomos"
    pick_species(filtered, "Al")
    assert filtered.count.text() == "1 de 4 átomos"  # the mark is in view
    pick_species(filtered, "O")
    assert filtered.count.text() == "1 de 4 átomos; 1 marcado fora do filtro"
    filtered.checks[3].click()
    assert filtered.count.text() == "2 de 4 átomos; 1 marcado fora do filtro"
    pick_species(filtered, "Todas")
    filtered.checks[1].click()
    pick_species(filtered, "O")
    assert filtered.count.text() == "3 de 4 átomos; 2 marcados fora do filtro"


def test_the_buttons_with_a_filter(filtered):
    """Spec 87 R5.6: "Marcar todos" and "Inverter" act on what is in view, "Desmarcar todos" on all."""
    heard = []
    filtered.changed.connect(lambda: heard.append(filtered.value()))
    pick_species(filtered, "O")
    filtered.mark_all.click()
    assert filtered.value() == (2, 3, 4)  # 1 is out of view, and stays unmarked
    filtered.invert.click()
    assert filtered.value() == (2,)  # 2 is out of view, and stays marked
    filtered.unmark_all.click()
    assert filtered.value() == ()
    assert heard == [(2, 3, 4), (2,), ()]


def test_set_rows_keeps_the_filter_while_the_species_is_listed(filtered):
    pick_species(filtered, "O")
    more = [*ROWS, AtomRow(5, "H", "1", "1", "1")]
    filtered.set_rows(more)
    assert filtered.species_button.text() == "Só espécie: O ▸"
    assert hidden(filtered) == [1, 2, 5]  # the new rows are filtered too
    assert [a.text() for a in filtered.species_menu.actions()] == ["Todas", "Al", "O", "H"]
    filtered.set_rows([AtomRow(1, "Al", "0", "0", "0"), AtomRow(5, "H", "1", "1", "1")])
    assert filtered.species_button.text() == "Só espécie ▸" and hidden(filtered) == []
    assert filtered.count.text() == "0 de 2 átomos"  # atom 2 left the list, and its mark too
    filtered.set_rows(ROWS)
    assert hidden(filtered) == []  # no row keeps the flag of the row number it had


def test_without_the_option_the_menu_marks_and_nothing_hides(table):
    assert table.species_button.toolTip() == ""
    table.species_menu.actions()[1].trigger()  # O
    assert table.value() == (3, 4) and hidden(table) == []
    assert table.species_button.text() == "Só espécie ▸" and table.count.text() == "2 de 4 átomos"
