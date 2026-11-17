"""Spec 105: the boxes and the numbers of the saw-like field in the "Criar cálculo" window, and the
warning under a field, which never blocks."""

import pytest
from PyQt6 import sip

from qe_studio.core.calc_create.types.dipole_fields import (
    DIPFIELD,
    EAMP,
    EDIR,
    EMAXPOS,
    EOPREG,
    IDLE_NOTE,
    INSIDE_NOTE,
    ONE_SIDE,
    POLAR_NOTE,
    RANGE_PROBLEM,
    TEFIELD,
)
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import to_files
from calc_helpers import JOBS
from surface_helpers import BULK

NUMBERS = (EDIR, EMAXPOS, EOPREG, EAMP)
ONE_SIDED = POLAR_NOTE.format(reason=ONE_SIDE)


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    return folder


@pytest.fixture
def make_dialog(qtbot, place, monkeypatch):
    # a clicked box is a user's edit: closing would ask whether to discard it
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)
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


def slab(qtbot, dialog: CalcCreateDialog):
    """Step 2 of a Slab from the kaolinite's bulk, whose SCF has no field."""
    return to_files(qtbot, dialog, "slab", scf=BULK, suffix="kao")


def written(tabs, key: str) -> str | None:
    editor = InputEditor.from_text(tabs.plan.by_key("relax").text)
    return editor.get("control" if key in (TEFIELD, DIPFIELD) else "system", key)


def test_the_boxes_start_off_and_the_warning_does_not_block(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = slab(qtbot, dialog)
    form = tabs.form_of(TEFIELD)
    assert not tabs.widget_of(TEFIELD).isChecked() and not tabs.widget_of(DIPFIELD).isChecked()
    assert form.shown(TEFIELD) and form.shown(DIPFIELD)
    assert not any(form.shown(key) for key in NUMBERS)
    assert form.advice(DIPFIELD) == ONE_SIDED  # why the slab needs it, under the box
    assert form.advice(TEFIELD) == ""
    assert ONE_SIDED in tabs.warnings()  # and with the plan's other notes
    assert dialog.create_button.isEnabled() and dialog.create_reason.isHidden()
    assert written(tabs, TEFIELD) is None


def test_the_numbers_show_with_tefield_and_open_filled(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = slab(qtbot, dialog)
    form = tabs.form_of(TEFIELD)
    tabs.widget_of(TEFIELD).click()
    assert all(form.shown(key) for key in NUMBERS)
    emaxpos, eopreg = tabs.widget_of(EMAXPOS), tabs.widget_of(EOPREG)
    assert emaxpos.text() == str(tabs.plan.auto[EMAXPOS]) and eopreg.text() == "0.1"
    assert emaxpos.placeholderText() == f"vazio = {emaxpos.text()} (automático)"
    assert tabs.values()[EMAXPOS] == ""  # what the plan shows is not a value the user typed
    assert (tabs.widget_of(EDIR).text(), tabs.widget_of(EAMP).text()) == ("3", "0.0")
    assert form.advice(TEFIELD) == IDLE_NOTE and form.advice(DIPFIELD) == ONE_SIDED
    assert written(tabs, TEFIELD) == ".true." and written(tabs, DIPFIELD) is None

    tabs.widget_of(DIPFIELD).click()  # the correction: nothing left to warn about
    assert form.advice(TEFIELD) == form.advice(DIPFIELD) == ""
    assert written(tabs, DIPFIELD) == ".true." and written(tabs, EMAXPOS) == emaxpos.text()
    assert dialog.create_button.isEnabled()

    tabs.widget_of(TEFIELD).click()  # off again: the numbers go, with what they warned
    assert not any(form.shown(key) for key in NUMBERS)
    assert written(tabs, EMAXPOS) is None and written(tabs, DIPFIELD) == ".true."
    assert form.advice(TEFIELD) != "" and form.advice(DIPFIELD) == ""


def test_a_typed_ramp_stays_warns_and_only_a_bad_one_blocks(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = slab(qtbot, dialog)
    form = tabs.form_of(TEFIELD)
    tabs.widget_of(TEFIELD).click()
    tabs.widget_of(DIPFIELD).click()
    emaxpos = tabs.widget_of(EMAXPOS)
    computed = emaxpos.text()
    emaxpos.setText("0.45")  # across the slab, which sits at the middle of the cell
    tabs.flush()
    assert written(tabs, EMAXPOS) == "0.45" and EMAXPOS not in tabs.plan.auto
    assert form.advice(EMAXPOS) == INSIDE_NOTE and dialog.create_button.isEnabled()
    emaxpos.setText("1.5")
    tabs.flush()
    assert not dialog.create_button.isEnabled()
    assert dialog.create_button.toolTip() == RANGE_PROBLEM.format(key=EMAXPOS)
    assert emaxpos.property("invalid") and form.advice(EMAXPOS) == ""
    emaxpos.setText("")  # emptied: back to the plan's
    tabs.flush()
    assert emaxpos.text() == computed and written(tabs, EMAXPOS) == computed
    assert dialog.create_button.isEnabled() and form.advice(EMAXPOS) == ""


def test_the_standard_mode_shows_the_boxes_only(qtbot, make_dialog):
    tabs = slab(qtbot, make_dialog("padrao"))
    form = tabs.form_of(TEFIELD)
    tabs.widget_of(TEFIELD).click()
    tabs.widget_of(DIPFIELD).click()
    assert form.shown(TEFIELD) and form.shown(DIPFIELD)
    assert not any(form.shown(key) for key in NUMBERS)
    assert written(tabs, EDIR) == "3" and written(tabs, EMAXPOS) == str(tabs.plan.auto[EMAXPOS])
