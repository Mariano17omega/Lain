"""The atom picker window and the "Átomos…" button of the PDOS panel (spec 21 R4, R5)."""

import pytest
from PyQt6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton

from atoms_helpers import pdos_folder
from qe_studio.core.compounds import AtomChoices, CompoundStore, compound_of
from qe_studio.core.qe.structure import Site
from qe_studio.ui.dialogs.atoms import NOTHING_MARKED, AtomsAnswer, AtomsDialog, ask_atoms

SITES = (
    Site(1, "Al", 0.0, 0.0, 0.0),
    Site(2, "Al", 1.5, 0.0, 0.25),
    Site(3, "O", -0.75, 2.0, 1.125),
    Site(4, "O", 3.0, -1.0, 0.5),
)
CHOICES = AtomChoices(SITES, compound_of(SITES))


@pytest.fixture
def dialog(qtbot):
    window = AtomsDialog(CHOICES, None)
    qtbot.addWidget(window)
    return window


def cell(dialog, row, column):
    return dialog.table.item(row, column).text()


# -- the window ---------------------------------------------------------------------------------
def test_lists_every_atom_with_its_coordinates(dialog):
    assert dialog.table.rowCount() == 4
    assert [cell(dialog, 2, c) for c in range(1, 6)] == ["3", "O", "-0.7500", "2.0000", "1.1250"]
    headers = [dialog.table.horizontalHeaderItem(c).text() for c in range(6)]
    assert headers[1:] == ["#", "Elemento", "x (Å)", "y (Å)", "z (Å)"]
    assert dialog.checked() == [1, 2, 3, 4]  # nothing saved yet: every atom
    assert dialog.heading.text() == "Átomos de Al2O2"


def test_shows_the_current_selection(qtbot):
    window = AtomsDialog(CHOICES, [2, 4])
    qtbot.addWidget(window)
    assert window.checked() == [2, 4]
    assert window.count.text() == "2 de 4 marcados"


def test_rows_follow_the_atom_number(qtbot):
    window = AtomsDialog(AtomChoices(tuple(reversed(SITES)), CHOICES.compound), None)
    qtbot.addWidget(window)
    assert [cell(window, r, 1) for r in range(4)] == ["1", "2", "3", "4"]


def test_the_checkbox_of_a_row_marks_that_atom(dialog):
    dialog.checks[2].click()
    assert dialog.checked() == [1, 3, 4]
    assert dialog.count.text() == "3 de 4 marcados"


def test_mark_all_unmark_all_and_invert(dialog):
    dialog.unmark_all.click()
    assert dialog.checked() == []
    dialog.checks[1].setChecked(True)
    dialog.checks[4].setChecked(True)
    dialog.invert.click()
    assert dialog.checked() == [2, 3]
    dialog.mark_all.click()
    assert dialog.checked() == [1, 2, 3, 4]


def test_only_one_species(dialog):
    actions = {a.text(): a for a in dialog.species_menu.actions()}
    assert list(actions) == ["Al", "O"]  # in the order they appear
    actions["O"].trigger()
    assert dialog.checked() == [3, 4]
    actions["Al"].trigger()
    assert dialog.checked() == [1, 2]


def test_save_with_nothing_marked_is_refused(dialog):
    dialog.unmark_all.click()
    dialog.save_button.click()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.problem.text() == NOTHING_MARKED
    dialog.checks[3].click()  # marking one clears the complaint
    assert dialog.problem.text() == ""


def test_save_answers_with_the_marked_atoms(dialog):
    dialog.unmark_all.click()
    dialog.checks[1].setChecked(True)
    dialog.checks[3].setChecked(True)
    dialog.save_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.answer() == AtomsAnswer([1, 3])


def test_every_atom_marked_answers_none(dialog):
    dialog.save_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.answer() == AtomsAnswer(None)


def test_cancel_rejects(dialog):
    dialog.unmark_all.click()
    dialog.cancel_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_ask_atoms_returns_the_answer_or_none(monkeypatch, qtbot):
    def accept_oxygen(self):
        self.only_species("O")
        self.save_button.click()
        return self.result()

    monkeypatch.setattr(AtomsDialog, "exec", accept_oxygen)
    assert ask_atoms(None, CHOICES, None) == AtomsAnswer([3, 4])  # type: ignore[arg-type]

    def cancel(self):
        self.cancel_button.click()
        return self.result()

    monkeypatch.setattr(AtomsDialog, "exec", cancel)
    assert ask_atoms(None, CHOICES, [1]) is None  # type: ignore[arg-type]


# -- the panel button ---------------------------------------------------------------------------
@pytest.fixture
def folders(demo_project):
    """Three PDOS folders: two of the same compound (Al O) and one with the order swapped."""
    return [
        pdos_folder(demo_project, species, name)
        for species, name in (
            (("Al", "O"), "05_ao"),
            (("Al", "O"), "06_ao"),
            (("O", "Al"), "07_oa"),
        )
    ]


def generate(qtbot, window, folder):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=False)
    return blocker.args[0]


def button_of(window):
    buttons = [b for b in window.params.body.findChildren(QPushButton) if b.text() == "Átomos…"]
    assert len(buttons) == 1
    return buttons[0]


def answer_with(monkeypatch, atoms, seen=None):
    def ask(parent, choices, selected):
        if seen is not None:
            seen.append((choices, selected))
        return None if atoms is False else AtomsAnswer(atoms)

    monkeypatch.setattr("qe_studio.ui.widgets.params_body.ask_atoms", ask)


def test_the_choice_is_saved_for_the_compound_and_replots(
    qtbot, window_factory, folders, monkeypatch
):
    window = window_factory()
    session = generate(qtbot, window, folders[0])
    button = button_of(window)
    assert button.isEnabled() and session.params.atoms is None
    seen = []
    answer_with(monkeypatch, [2], seen)
    button.click()
    choices, selected = seen[0]
    assert [s.species for s in choices.sites] == ["Al", "O"] and selected is None
    assert session.params.atoms == [2]
    key = session.dataset.compound.key
    assert CompoundStore(window.compounds.path).selection(key) == [2]
    qtbot.waitUntil(lambda: "1 de 2 átomos" in (session.info.summary if session.info else ""))
    window.plot_settings.flush_now()
    assert not (folders[0] / "pdos.plot").exists()  # picking atoms is not a plot edit


def test_another_folder_of_the_same_compound_opens_filtered(
    qtbot, window_factory, folders, monkeypatch
):
    window = window_factory()
    generate(qtbot, window, folders[0])
    answer_with(monkeypatch, [2])
    button_of(window).click()
    assert generate(qtbot, window, folders[1]).params.atoms == [2]
    assert (
        generate(qtbot, window, folders[2]).params.atoms is None
    )  # Al/O swapped: another compound


def test_the_choice_survives_a_restart_and_a_regenerate(
    qtbot, window_factory, folders, monkeypatch
):
    window = window_factory()
    generate(qtbot, window, folders[0])
    answer_with(monkeypatch, [1])
    button_of(window).click()
    window.plot_settings.flush_now()
    window.close()
    restarted = window_factory()  # same files in tmp_path
    assert generate(qtbot, restarted, folders[1]).params.atoms == [1]
    answer_with(monkeypatch, None)  # now every atom
    button_of(restarted).click()
    again = generate(qtbot, restarted, folders[1])  # regenerate: the store, not the old tab
    assert again.params.atoms is None


def test_cancelling_changes_nothing(qtbot, window_factory, folders, monkeypatch):
    window = window_factory()
    session = generate(qtbot, window, folders[0])
    answer_with(monkeypatch, False)
    button_of(window).click()
    assert session.params.atoms is None
    assert not window.compounds.path.exists()


def test_restoring_the_defaults_keeps_the_compounds_atoms(
    qtbot, window_factory, folders, monkeypatch
):
    window = window_factory()
    session = generate(qtbot, window, folders[0])
    answer_with(monkeypatch, [2])
    button_of(window).click()
    session.params.emin = -2.0
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    window.plot_workflow.restore_defaults()
    assert session.params.emin == -5.0 and session.params.atoms == [2]


def test_the_summary_beside_the_button(qtbot, window_factory, folders, monkeypatch):
    window = window_factory()
    generate(qtbot, window, folders[0])
    button = button_of(window)
    summary = button.parentWidget().findChild(QLabel)
    assert summary.text() == "todos"
    answer_with(monkeypatch, [2])
    button.click()
    assert summary.text() == "1 de 2"
    window.params.refresh_values()  # e.g. after a pan: still what the parameter says
    assert summary.text() == "1 de 2"


def test_without_readable_atoms_the_button_is_disabled(qtbot, window_factory, demo_project):
    folder = pdos_folder(demo_project, ("Al", "O"), "08_unreadable")
    for name in ("scf.out", "nscf.out"):
        (folder / name).write_text((folder / name).read_text().replace("tau(", "xyz("))
    window = window_factory()
    generate(qtbot, window, folder)
    button = button_of(window)
    assert not button.isEnabled()
    assert button.toolTip() == "Não foi possível ler os átomos da saída do SCF"
