"""Spec 40 R1: a second SCF as a field of "Criar cálculo" (the molecule of the Slab type), read in a
worker, and the report ``geracao.md`` in the window."""

from __future__ import annotations

import threading

import pytest
from PyQt6 import sip

from qe_studio.core.calc_create.preview import file_rows
from qe_studio.core.calc_create.scf_info import ScfInfo
from qe_studio.core.calc_create.surface.report import REPORT_KEY
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog, scf_field, setup_page
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.scf_field import READING, ScfFileField
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import to_files, type_in_preview
from calc_helpers import AL_SCF, JOBS
from surface_helpers import BULK, MOLECULE


@pytest.fixture
def make_dialog(qtbot, tmp_path):
    place = tmp_path / "proj"
    place.mkdir()
    made = []

    def make(mode="avancado") -> CalcCreateDialog:
        window = CalcCreateDialog(ThemeManager("dark"), place, place, JOBS)
        window.set_mode(mode)
        window.show()
        made.append(window)
        return window

    yield make
    for window in made:
        if not sip.isdeleted(window):
            window.close()


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


@pytest.fixture
def chosen(monkeypatch):
    """``choose_scf``, patched: the file it answers (``chosen.path``) and where it opened."""

    def choose(parent, start):
        choose.starts.append(start)
        return choose.path

    choose.path = MOLECULE
    choose.starts = []
    monkeypatch.setattr(setup_page, "choose_scf", choose)
    return choose


def slab_tabs(qtbot, make_dialog, mode="avancado"):
    dialog = make_dialog(mode)
    tabs = to_files(qtbot, dialog, "slab", scf=BULK, suffix="kao")
    return dialog, tabs, tabs.widget_of("molecule")


def report(tabs) -> str:
    return tabs.plan.by_key(REPORT_KEY).text


def pick(qtbot, field: ScfFileField) -> None:
    with qtbot.waitSignal(field.changed, timeout=10_000):
        field.choose_button.click()


def test_the_slab_tabs(qtbot, make_dialog):
    _dialog, tabs, field = slab_tabs(qtbot, make_dialog)
    assert tabs.tab_labels() == [
        "Superfície",
        "Script (slab.qsub)",
        "Slab (vc-relax_kaolinite.in)",
        "Relatório (geracao.md)",
        "Arquivos",
        "Descrição",
    ]
    assert isinstance(field, ScfFileField) and field.value() is None
    assert "geracao.md" in tabs.files_view.names()


def test_choosing_a_scf_fills_the_field_and_plans_again(qtbot, make_dialog, chosen):
    _dialog, tabs, field = slab_tabs(qtbot, make_dialog)
    assert "Molécula" not in report(tabs)
    pick(qtbot, field)
    assert chosen.starts == [BULK.parent]  # the SCF's folder
    assert isinstance(field.value(), ScfInfo) and field.value().name == MOLECULE.name
    assert field.message.isHidden() and field.edit.text() == str(MOLECULE)
    assert "Molécula" in report(tabs) and "15.10 Å" in report(tabs)
    assert tabs.dirty


def test_the_field_is_in_the_standard_mode(qtbot, make_dialog, chosen):
    _dialog, tabs, field = slab_tabs(qtbot, make_dialog, mode="padrao")
    assert tabs.form_shown("Superfície") and tabs.form_of("molecule").shown("molecule")
    pick(qtbot, field)
    assert "Molécula" in report(tabs)


def test_a_file_that_is_no_input_leaves_the_field_empty(qtbot, make_dialog, chosen, tmp_path):
    _dialog, tabs, field = slab_tabs(qtbot, make_dialog)
    notes = tmp_path / "notas.txt"
    notes.write_text("só texto\n")
    chosen.path = notes
    pick(qtbot, field)
    assert field.value() is None
    assert field.message.text() == "notas.txt não parece um input do Quantum ESPRESSO"
    assert field.message.property("variant") == "dialogError"
    relax = tmp_path / "relax.in"
    relax.write_text(AL_SCF.read_text().replace("'scf'", "'relax'"))
    chosen.path = relax
    pick(qtbot, field)
    assert field.value() is None
    assert field.message.text() == "O arquivo não é um SCF (calculation = 'relax')"
    assert "Molécula" not in report(tabs)


def test_clearing_empties_the_field(qtbot, make_dialog, chosen):
    _dialog, tabs, field = slab_tabs(qtbot, make_dialog)
    pick(qtbot, field)
    assert field.clear_button.isEnabled()
    with qtbot.waitSignal(field.changed, timeout=1000):
        field.clear_button.click()
    assert field.value() is None and field.edit.text() == ""
    assert not field.clear_button.isEnabled()
    assert "Molécula" not in report(tabs)


def test_closing_the_window_while_reading_calls_nothing_back(
    qtbot, make_dialog, chosen, monkeypatch
):
    release, started = threading.Event(), threading.Event()
    real = scf_field.read_other_scf

    def slow(path):
        started.set()
        release.wait(5)
        return real(path)

    called = []
    monkeypatch.setattr(scf_field, "read_other_scf", slow)
    monkeypatch.setattr(ScfFileField, "_on_read", lambda self, key, info: called.append(info))
    dialog, _tabs, field = slab_tabs(qtbot, make_dialog)
    field.choose_button.click()
    assert started.wait(5)
    assert field.reading and field.message.text() == READING
    dialog.close()
    release.set()
    qtbot.wait(300)
    assert called == []


def test_the_report_can_be_edited_in_the_advanced_mode(qtbot, make_dialog):
    """Spec 39 R2 holds for it too; Markdown is never linted."""
    _dialog, tabs, _field = slab_tabs(qtbot, make_dialog)
    type_in_preview(qtbot, tabs, REPORT_KEY, "Nota minha.")
    assert report(tabs).endswith("Nota minha.\n")
    assert not tabs.previews[REPORT_KEY].diagnostics
    rows = file_rows(tabs.plan.files, tabs.edited_keys())
    assert ("geracao.md", "Relatório (editado)") in [(row.name, row.kind) for row in rows]
