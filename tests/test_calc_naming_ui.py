"""Spec 77 R2: "Sítio no nome" and "Herdar sufixo do SCF" in step 1 of "Criar cálculo", and the
name they give the folder."""

from __future__ import annotations

import shutil

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings

from qe_studio.ui.dialogs.calc_create import CalcCreateDialog, setup_page
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import fill_setup, to_files, tree
from calc_helpers import AL_SCF, JOBS
from surface_helpers import MOLECULE, SUPERCELL_001

SCF_FOLDER = "1_Adsorption_teste_O11"


@pytest.fixture
def place(tmp_path):
    """A place with two numbered folders; the second one holds the surface SCF."""
    folder = tmp_path / "proj"
    (folder / "0_Relax").mkdir(parents=True)
    (folder / SCF_FOLDER).mkdir()
    shutil.copy(SUPERCELL_001, folder / SCF_FOLDER / SUPERCELL_001.name)
    return folder


@pytest.fixture
def surface(place):
    return place / SCF_FOLDER / SUPERCELL_001.name


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


@pytest.fixture
def make_dialog(qtbot, place):
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


def mark_site(qtbot, dialog, monkeypatch, number=43):
    """Step 2 of a molecule on a surface with the molecule and the site chosen."""
    monkeypatch.setattr(setup_page, "choose_scf", lambda parent, start: MOLECULE)
    tabs = dialog.tabs
    assert tabs is not None
    field = tabs.widget_of("molecule")
    with qtbot.waitSignal(field.changed, timeout=10_000):
        field.choose_button.click()
    tabs.widget_of("site").checks[number].click()
    tabs.widget_of("remove_h").click()
    return tabs


def test_the_boxes_show_only_when_they_apply(qtbot, dialog, surface):
    setup = dialog.setup
    assert setup.site_check.isHidden() and setup.inherit_check.isHidden()
    fill_setup(qtbot, dialog, "adsorption", scf=surface)
    assert not setup.site_check.isHidden()
    assert not setup.inherit_check.isHidden()
    assert setup.inherit_check.text() == "Herdar sufixo do SCF (teste_O11)"
    dialog.setup.set_type("bandas")
    assert setup.site_check.isHidden() and not setup.inherit_check.isHidden()
    fill_setup(qtbot, dialog, "adsorption", scf=AL_SCF)  # not in a folder with a suffix
    assert not setup.site_check.isHidden() and setup.inherit_check.isHidden()
    assert setup.inherited == ""  # nothing to inherit, nothing asked


def test_a_hidden_box_asks_nothing(qtbot, dialog, surface):
    fill_setup(qtbot, dialog, "bandas", scf=surface)
    dialog.setup.site_check.setChecked(True)  # the type has no site
    dialog.setup.inherit_check.setChecked(True)
    assert dialog.setup.inherited == "teste_O11" and not dialog.setup.site_tag
    fill_setup(qtbot, dialog, "bandas", scf=AL_SCF)  # no suffix to inherit
    assert dialog.setup.inherited == ""


def test_step_1_names_the_folder_with_the_inherited_suffix_and_a_site_to_come(
    qtbot, dialog, surface
):
    fill_setup(qtbot, dialog, "adsorption", scf=surface, suffix="x")
    preview = dialog.setup.name_preview
    assert preview.text() == "Será criada: Adsorption_x"
    dialog.setup.number_check.setChecked(True)
    dialog.setup.inherit_check.setChecked(True)
    assert preview.text() == "Será criada: 2_Adsorption_x_teste_O11"
    dialog.setup.site_check.setChecked(True)
    assert preview.text() == "Será criada: 2_Adsorption_x_teste_O11_<sítio>"
    dialog.setup.inherit_check.setChecked(False)
    assert preview.text() == "Será criada: 2_Adsorption_x_<sítio>"


def test_every_box_marked_names_the_folder(qtbot, main_window, place, surface, monkeypatch):
    window = main_window
    window.use_session_root(place)
    window.activity.new_calc.click()
    dialog = window.calc_create.dialog
    assert dialog is not None
    dialog.setup.number_check.setChecked(True)
    dialog.setup.site_check.setChecked(True)
    dialog.setup.inherit_check.setChecked(False)  # set before: the SCF decides if it shows
    tabs = to_files(qtbot, dialog, "adsorption", scf=surface, suffix="x", location=place)
    dialog.setup.inherit_check.setChecked(True)
    dialog.back_button.click()
    dialog.continue_button.click()
    assert dialog.tabs is tabs
    tabs = mark_site(qtbot, dialog, monkeypatch)
    assert tabs.plan.folder_tag == "O43"
    assert tabs.files_view.target.text() == f"Pasta: {place / '2_Adsorption_x_teste_O11_O43'}"
    with qtbot.waitSignal(window.calc_create.created, timeout=10_000) as blocker:
        dialog.create_button.click()
    assert blocker.args[0].folder == place / "2_Adsorption_x_teste_O11_O43"
    notice = window.toast.current
    assert notice is not None and "Pasta 2_Adsorption_x_teste_O11_O43 criada" in notice.text


def test_the_name_follows_the_site_and_says_when_there_is_none(
    qtbot, dialog, surface, place, monkeypatch
):
    dialog.setup.site_check.setChecked(True)
    tabs = to_files(qtbot, dialog, "adsorption", scf=surface, suffix="", location=place)
    target = tabs.files_view.target
    assert target.text() == f"Pasta: {place / 'Adsorption'}"  # no site yet
    assert "Sem sítio: o nome fica sem a marca" in tabs.warnings()
    tabs = mark_site(qtbot, dialog, monkeypatch, 43)
    assert target.text() == f"Pasta: {place / 'Adsorption_O43'}"
    assert "Sem sítio: o nome fica sem a marca" not in tabs.warnings()
    tabs.widget_of("site").checks[43].click()
    tabs.widget_of("site").checks[46].click()
    assert target.text() == f"Pasta: {place / 'Adsorption_O46'}"
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert blocker.args[0].tag == "O46" and blocker.args[0].inherited == ""
    assert tree(place) == [
        "0_Relax",
        SCF_FOLDER,
        f"{SCF_FOLDER}/{SUPERCELL_001.name}",
    ]  # the window never writes


def test_unchecked_boxes_keep_todays_name(qtbot, dialog, surface, place, monkeypatch):
    tabs = to_files(qtbot, dialog, "adsorption", scf=surface, suffix="x", location=place)
    tabs = mark_site(qtbot, dialog, monkeypatch)
    assert tabs.files_view.target.text() == f"Pasta: {place / 'Adsorption_x'}"
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert (blocker.args[0].inherited, blocker.args[0].tag) == ("", "")


def test_the_choices_are_remembered(make_dialog, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    first = make_dialog(settings)
    assert not first.setup.site_check.isChecked() and not first.setup.inherit_check.isChecked()
    first.setup.site_check.setChecked(True)
    first.setup.inherit_check.setChecked(True)
    assert settings.value("calc_create/site_tag", type=bool) is True
    assert settings.value("calc_create/inherit_suffix", type=bool) is True
    first.close()
    again = make_dialog(settings)
    assert again.setup.site_check.isChecked() and again.setup.inherit_check.isChecked()
    again.setup.site_check.setChecked(False)
    assert settings.value("calc_create/site_tag", type=bool) is False
    assert not make_dialog().setup.site_check.isChecked()  # no settings: unchecked
