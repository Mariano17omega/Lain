"""Spec 80 R2: the "Gerar fingerprint.md" box of step 1 and its row in the "Arquivos" tab."""

import shutil
from datetime import datetime

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings

from qe_studio.core.calc_create.fingerprint import FINGERPRINT_NAME, Source, fingerprint_text
from qe_studio.core.calc_create.scf_info import read_scf
from qe_studio.core.calc_create.types import REGISTRY, by_id
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.setup_page import FINGERPRINT_TIP
from qe_studio.ui.dialogs.calc_create.tabs_page import TabsPage
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import to_files, tree
from calc_helpers import AL_SCF, JOBS, SI_SCF

WHEN = datetime(2026, 10, 31, 14, 5, 9)


@pytest.fixture
def place(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    return folder


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


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


def test_the_box_starts_unchecked_and_says_what_it_does(dialog):
    box = dialog.setup.fingerprint_check
    assert box.text() == "Gerar fingerprint.md" and box.toolTip() == FINGERPRINT_TIP
    assert not box.isChecked() and not dialog.setup.fingerprint


@pytest.mark.parametrize("calc_type", REGISTRY, ids=lambda t: t.id)
def test_every_type_shows_the_box(dialog, calc_type):
    dialog.setup.set_type(calc_type.id)
    assert dialog.setup.fingerprint_check.isVisibleTo(dialog.setup)


def test_the_choice_is_remembered(make_dialog, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    first = make_dialog(settings)
    first.setup.fingerprint_check.setChecked(True)
    assert settings.value("calc_create/fingerprint", type=bool) is True
    first.close()
    again = make_dialog(settings)
    assert again.setup.fingerprint
    again.setup.fingerprint_check.setChecked(False)
    assert settings.value("calc_create/fingerprint", type=bool) is False
    assert not make_dialog(settings).setup.fingerprint
    assert not make_dialog().setup.fingerprint  # no settings: unchecked


def test_unchecked_there_is_no_row_and_no_sources(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    assert FINGERPRINT_NAME not in tabs.files_view.names()
    assert tabs.fingerprint_sources() is None
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    assert blocker.args[0].fingerprint is None
    assert tree(dialog.setup.location) == []  # the window never writes


def test_checked_the_files_tab_lists_it_and_the_request_carries_it(qtbot, dialog, place):
    dialog.setup.fingerprint_check.setChecked(True)
    tabs = to_files(qtbot, dialog, "pdos")
    view = tabs.files_view
    assert FINGERPRINT_NAME in view.names()
    row = view.tree.topLevelItem(view.names().index(FINGERPRINT_NAME))
    assert row.text(1) == "Anotações"
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    request = blocker.args[0]
    assert request.fingerprint == (Source("Input de SCF", AL_SCF),) and request.root == place


def test_the_box_can_change_on_step_1_after_step_2_was_built(qtbot, dialog):
    tabs = to_files(qtbot, dialog, "pdos")
    assert FINGERPRINT_NAME not in tabs.files_view.names()
    dialog.back_button.click()
    dialog.setup.fingerprint_check.setChecked(True)
    dialog.continue_button.click()
    assert dialog.tabs is tabs  # the box does not build step 2 again
    assert FINGERPRINT_NAME in tabs.files_view.names()
    dialog.back_button.click()
    dialog.setup.fingerprint_check.setChecked(False)
    dialog.continue_button.click()
    assert FINGERPRINT_NAME not in tabs.files_view.names()


def test_the_preview_does_not_read_the_disk_and_names_the_folder(qtbot, dialog, place):
    dialog.setup.fingerprint_check.setChecked(True)
    dialog.setup.number_check.setChecked(True)
    (place / "4_Relax").mkdir()
    tabs = to_files(qtbot, dialog, "pdos")
    text = tabs._fingerprint_preview("5_PDOS_Al")
    assert text is not None and "`5_PDOS_Al`" in text and f"`{AL_SCF}`" in text


def test_the_preview_follows_links_as_the_writer_does(qtbot, make_dialog, tmp_path):
    """The root reached through a link and the SCF by its real path: the preview of the "Arquivos"
    tab names the SCF relative to the root once a worker resolved the paths, as the file written
    will (``fingerprint_text`` with the disk)."""
    real = tmp_path / "real"
    (real / "proj").mkdir(parents=True)
    scf = real / "proj" / "al.scf.in"
    shutil.copyfile(AL_SCF, scf)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    window = CalcCreateDialog(ThemeManager("dark"), link, link / "proj", JOBS)
    window.show()
    try:
        window.setup.fingerprint_check.setChecked(True)
        tabs = to_files(qtbot, window, "pdos", scf=scf, location=link / "proj")
        found = [Source("Input de SCF", scf)]
        written = fingerprint_text(tabs.calc_type, "PDOS_Al", found, link, WHEN)
        assert "`proj/al.scf.in`" in written

        def rows(text: str | None) -> list[str]:
            """The table but its time, which is the moment each is made."""
            return [line for line in (text or "").splitlines() if "Criado em" not in line]

        qtbot.waitUntil(
            lambda: rows(tabs._fingerprint_preview("PDOS_Al")) == rows(written), timeout=5000
        )
    finally:
        window.close()


def test_with_the_fingerprint_the_notes_do_not_list_the_scfs_again(qtbot, dialog):
    """Spec 79's notes say where the SCFs came from; ``fingerprint.md`` already does, so with the box
    on they start empty. What the user typed is never replaced."""
    tabs = to_files(qtbot, dialog, "ads_energy")
    assert tabs.notes_text().startswith("SCFs de origem:")
    dialog.back_button.click()
    dialog.setup.fingerprint_check.setChecked(True)
    dialog.continue_button.click()
    assert tabs.notes_text() == "" and not tabs.dirty
    dialog.back_button.click()
    dialog.setup.fingerprint_check.setChecked(False)
    dialog.continue_button.click()
    assert tabs.notes_text().startswith("SCFs de origem:")
    tabs.notes.setPlainText("minhas notas")
    dialog.back_button.click()
    dialog.setup.fingerprint_check.setChecked(True)
    dialog.continue_button.click()
    assert tabs.notes_text() == "minhas notas"


@pytest.fixture
def linked_page(qtbot, tmp_path):
    """Step 2 of "Energia de adsorção" for a project whose root is a link: its SCFs given by their real
    paths, and the root by the link."""
    real = tmp_path / "real"
    (real / "proj").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    paths = [real / "proj" / AL_SCF.name, real / "proj" / SI_SCF.name]
    shutil.copy(AL_SCF, paths[0])
    shutil.copy(SI_SCF, paths[1])
    scfs = tuple(read_scf(path) for path in paths)
    page = TabsPage(ThemeManager("dark"), by_id("ads_energy"), scfs[0], JOBS, scfs=scfs, root=link)
    qtbot.addWidget(page)
    yield page
    page.shutdown()


def test_the_notes_name_the_scfs_from_a_root_that_is_a_link(qtbot, linked_page):
    expected = f"SCFs de origem:\n- proj/{AL_SCF.name}\n- proj/{SI_SCF.name}\n"
    qtbot.waitUntil(lambda: linked_page.notes_text() == expected, timeout=5000)
    assert not linked_page.dirty  # what the page starts with, not something the user typed


def test_what_the_user_typed_in_the_notes_stays_when_the_paths_arrive(qtbot, linked_page):
    linked_page.notes.setPlainText("anotação")
    qtbot.waitUntil(lambda: bool(linked_page._real), timeout=5000)
    assert linked_page.notes_text() == "anotação"
