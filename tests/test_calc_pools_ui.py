"""Spec 102: the pools field of the "Criar cálculo" window shows what the plan computed, until typed in."""

import pytest
from PyQt6 import sip

from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import to_files
from calc_helpers import JOBS


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    return folder


@pytest.fixture
def make_dialog(qtbot, place):
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


def nk_line(tabs) -> str:
    [line] = [x for x in tabs.plan.files[0].text.splitlines() if x.startswith("NK=")]
    return line


def test_the_field_opens_filled_with_the_computed_pools(qtbot, make_dialog):
    tabs = to_files(qtbot, make_dialog(), "scf")
    nk = tabs.widget_of("nk")
    assert nk.text() == "16" and nk.placeholderText() == "vazio = 16 (automático)"
    assert tabs.values()["nk"] == ""  # what the plan shows is not a value the user typed
    assert nk_line(tabs) == "NK=16" and tabs.plan.auto == {"nk": 16}


def test_the_field_follows_np_until_the_user_types(qtbot, make_dialog):
    tabs = to_files(qtbot, make_dialog(), "scf")
    tabs.widget_of("np").setText("32")
    tabs.flush()
    assert tabs.widget_of("nk").text() == "8" and nk_line(tabs) == "NK=8"
    tabs.widget_of("np").setText("128")
    tabs.flush()
    assert tabs.widget_of("nk").text() == "16" and nk_line(tabs) == "NK=16"


def test_a_typed_value_stays_and_an_emptied_field_goes_back(qtbot, make_dialog):
    tabs = to_files(qtbot, make_dialog(), "scf")
    nk = tabs.widget_of("nk")
    nk.setText("4")  # a user's edit, whatever shows it
    tabs.flush()
    assert nk_line(tabs) == "NK=4" and tabs.values()["nk"] == "4" and tabs.plan.auto == {}
    tabs.widget_of("np").setText("32")
    tabs.flush()
    assert nk.text() == "4" and nk_line(tabs) == "NK=4"  # NP changed, the typed value did not
    nk.setText("")
    tabs.flush()
    assert nk.text() == "8" and nk_line(tabs) == "NK=8" and tabs.plan.auto == {"nk": 8}


def test_the_field_shows_the_value_the_standard_mode_would_use(qtbot, make_dialog):
    tabs = to_files(qtbot, make_dialog("padrao"), "relax")
    assert not tabs.form_of("nk").shown("nk")  # hidden in the Padrão mode ...
    assert nk_line(tabs) == "NK=16"  # ... but the script has it
    assert tabs.widget_of("nk").text() == "16"
