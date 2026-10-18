"""Spec 51 R2: the "Numerar" box of step 1 of "Criar cálculo"."""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings

from qe_studio.core.calc_create.types import REGISTRY
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.setup_page import NUMBER_TIP
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import fill_setup, to_files, tree
from calc_helpers import JOBS


@pytest.fixture
def place(tmp_path):
    """A place that already holds two numbered folders of other types."""
    folder = tmp_path / "proj"
    for name in ("0_Relax", "1_Bands"):
        (folder / name).mkdir(parents=True)
    return folder


@pytest.fixture
def make_dialog(qtbot, place):
    """New windows on ``place``, closed at teardown unless a test closed (deleted) them."""
    made = []

    def make(settings=None) -> CalcCreateDialog:
        window = CalcCreateDialog(ThemeManager("dark"), place, place, JOBS, settings=settings)
        window.show()
        made.append(window)
        return window

    yield make
    for window in made:
        if not sip.isdeleted(window):
            window.close()


@pytest.fixture
def dialog(make_dialog):
    return make_dialog()


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


def preview_of(dialog) -> str:
    return dialog.setup.name_preview.text()


def test_the_box_starts_unchecked(dialog):
    box = dialog.setup.number_check
    assert box.objectName() == "numberCheck" and box.text() == "Numerar"
    assert box.accessibleName() == "Numerar" and box.toolTip() == NUMBER_TIP
    assert not box.isChecked() and box.isEnabled() and not dialog.setup.numbered


def test_checking_numbers_the_preview(qtbot, dialog):
    fill_setup(qtbot, dialog, "bandas")
    assert preview_of(dialog) == "Será criada: Bands_Al"
    dialog.setup.number_check.setChecked(True)
    assert preview_of(dialog) == "Será criada: 2_Bands_Al"
    dialog.setup.number_check.setChecked(False)
    assert preview_of(dialog) == "Será criada: Bands_Al"


@pytest.mark.parametrize("calc_type", REGISTRY, ids=lambda t: t.id)
def test_every_type_can_be_numbered(dialog, calc_type):
    """The step 1 preview needs no SCF; no type turns the box off (PDOS included)."""
    setup = dialog.setup
    setup.set_type(calc_type.id)
    setup.suffix_edit.setText("Al")
    setup.number_check.setChecked(True)
    assert setup.number_check.isEnabled()
    assert preview_of(dialog) == f"Será criada: 2_{calc_type.folder_prefix}_Al"


def test_the_number_follows_the_place(dialog, tmp_path):
    setup = dialog.setup
    setup.set_type("pdos")
    setup.suffix_edit.setText("Al")
    setup.number_check.setChecked(True)
    other = tmp_path / "outro"
    (other / "7_x").mkdir(parents=True)
    setup.set_location(other)
    assert preview_of(dialog) == "Será criada: 8_PDOS_Al"
    (other / "8_PDOS").mkdir()  # the place changed: the next update counts it
    setup.suffix_edit.setText("Fe")
    assert preview_of(dialog) == "Será criada: 9_PDOS_Fe"


def test_the_files_tab_and_the_request_carry_it(qtbot, dialog, place):
    dialog.setup.number_check.setChecked(True)
    tabs = to_files(qtbot, dialog, "pdos")
    assert tabs.files_view.target.text() == f"Pasta: {place / '2_PDOS_Al'}"
    assert "2_PDOS_Al_1" in tabs.files_view.note.text()
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert blocker.args[0].numbered is True
    dialog.back_button.click()
    dialog.setup.number_check.setChecked(False)
    dialog.continue_button.click()
    assert dialog.tabs is tabs  # the box does not build step 2 again
    assert tabs.files_view.target.text() == f"Pasta: {place / 'PDOS_Al'}"
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert blocker.args[0].numbered is False
    assert tree(place) == ["0_Relax", "1_Bands"]  # the window never writes


def test_the_choice_is_remembered(make_dialog, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    first = make_dialog(settings)
    assert not first.setup.numbered  # the first time
    first.setup.number_check.setChecked(True)
    assert settings.value("calc_create/numbered", type=bool) is True
    first.close()
    again = make_dialog(settings)
    assert again.setup.numbered
    assert preview_of(again) == ""  # no type yet: nothing to name
    again.setup.number_check.setChecked(False)
    assert settings.value("calc_create/numbered", type=bool) is False
    assert not make_dialog(settings).setup.numbered
    assert not make_dialog().setup.numbered  # no settings: unchecked
