"""Spec 79 R1: step 1 of "Criar cálculo" takes a list of SCFs for a ``multi_scf`` type.

A type of one SCF keeps its field; "Energia de adsorção" shows the list ("Adicionar…", "Remover"),
needs two SCFs read without error before "Continuar", refuses a file already in the list, and step 2
gets a tab per SCF, each compared with its own SCF.
"""

import shutil

import pytest
from PyQt6 import sip

from qe_studio.core.calc_create.types.ads_energy import SAME_PREFIX
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog, scf_list
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.scf_list import READING, TOO_FEW
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import add_scfs, pick_scf
from calc_helpers import AL_SCF, JOBS, NI_SCF, SI_SCF

TYPE = "ads_energy"


@pytest.fixture
def dialog(qtbot, tmp_path):
    place = tmp_path / "proj"
    place.mkdir()
    window = CalcCreateDialog(ThemeManager("dark"), place, place, JOBS)
    window.set_mode("avancado")
    window.debounce_ms = 0
    window.show()
    yield window
    if not sip.isdeleted(window):
        window.close()


@pytest.fixture(autouse=True)
def asked(monkeypatch):
    calls = []
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: calls.append(parent) or True)
    return calls


def reason(dialog) -> str:
    return "" if dialog.setup.reason.isHidden() else dialog.setup.reason.text()


def test_the_list_replaces_the_field_only_for_its_type(dialog):
    setup = dialog.setup
    setup.set_type("scf")
    assert not setup.scf_box.isHidden() and not setup.scf_label.isHidden()
    assert setup.scf_list.isHidden() and setup.scfs_label.isHidden()
    setup.set_type(TYPE)
    assert setup.scf_box.isHidden() and setup.scf_label.isHidden()
    assert not setup.scf_list.isHidden()
    assert setup.scfs_label.text() == "Inputs de SCF *"
    assert setup.scf_list.list.accessibleName() == "Inputs de SCF"
    setup.set_type("pdos")
    assert not setup.scf_box.isHidden() and setup.scf_list.isHidden()


def test_continue_needs_two_scfs(qtbot, dialog):
    setup = dialog.setup
    setup.set_type(TYPE)
    assert reason(dialog) == TOO_FEW and not dialog.continue_button.isEnabled()
    with qtbot.waitSignal(setup.scf_list.changed):  # the reading is said while it lasts
        setup.scf_list.add_paths([SI_SCF])
        assert reason(dialog) == READING
    qtbot.waitUntil(lambda: not setup.scf_list.reading)
    assert reason(dialog) == TOO_FEW and not dialog.continue_button.isEnabled()
    assert setup.scf is None and setup.scfs == ()
    add_scfs(qtbot, dialog, [AL_SCF])
    assert reason(dialog) == "" and dialog.continue_button.isEnabled()
    assert [scf.path for scf in setup.scfs] == [SI_SCF, AL_SCF]
    assert setup.scf is setup.scfs[0]
    assert setup.scf_list.list.item(0).text() == f"{SI_SCF} · prefix silicon, 2 átomos"


def test_two_scfs_open_step_2_with_a_tab_each(qtbot, dialog):
    dialog.setup.set_type(TYPE)
    add_scfs(qtbot, dialog, [SI_SCF, AL_SCF, NI_SCF])
    dialog.continue_button.click()
    assert dialog.on_files_step()
    tabs = dialog.tabs
    assert tabs.tab_labels() == [
        "Script (ads_energy.qsub)",
        "SCF (scf_silicon.in)",
        "SCF (scf_al.in)",
        "SCF (scf_ni.in)",
        "Arquivos",
        "Descrição",
    ]
    assert dialog.create_button.isEnabled(), dialog.create_button.toolTip()
    for key in ("scf0", "scf1", "scf2"):  # each compared with its own SCF, not the first
        preview = tabs.previews[key]
        rows = [preview.toPlainText().splitlines()[row] for row in preview.changed_rows()]
        assert len(rows) == 1 and "outdir" in rows[0], (key, rows)
    assert tabs.notes_text() == f"SCFs de origem:\n- {SI_SCF}\n- {AL_SCF}\n- {NI_SCF}\n"
    assert not tabs.dirty  # the notes it starts with are no edit


def test_removing_one_goes_back_to_the_reason_and_rebuilds(qtbot, dialog):
    setup = dialog.setup
    setup.set_type(TYPE)
    add_scfs(qtbot, dialog, [SI_SCF, AL_SCF])
    dialog.continue_button.click()
    dialog.back_button.click()
    setup.scf_list.list.item(1).setSelected(True)
    setup.scf_list.remove_button.click()
    assert setup.scf_list.paths == [SI_SCF]
    assert reason(dialog) == TOO_FEW and not dialog.continue_button.isEnabled()
    add_scfs(qtbot, dialog, [NI_SCF])
    assert not setup.rebuild_note.isHidden()  # another list: step 2 is built again
    dialog.continue_button.click()
    assert [planned.name for planned in dialog.tabs.plan.files][1:] == [
        "scf_silicon.in",
        "scf_ni.in",
    ]


def test_the_same_file_twice_is_refused(qtbot, dialog):
    setup = dialog.setup
    setup.set_type(TYPE)
    add_scfs(qtbot, dialog, [SI_SCF, AL_SCF])
    add_scfs(qtbot, dialog, [AL_SCF])
    assert setup.scf_list.paths == [SI_SCF, AL_SCF]
    assert setup.scf_list.message.text() == "al.scf.in já está na lista"
    assert dialog.continue_button.isEnabled()


def test_a_file_that_is_not_an_scf_blocks_with_its_name(qtbot, dialog, tmp_path):
    setup = dialog.setup
    setup.set_type(TYPE)
    relax = tmp_path / "relax.in"
    relax.write_text(AL_SCF.read_text().replace("'scf'", "'relax'"))
    add_scfs(qtbot, dialog, [SI_SCF, AL_SCF, relax])
    assert reason(dialog) == "relax.in: O arquivo não é um SCF (calculation = 'relax')"
    assert not dialog.continue_button.isEnabled()
    setup.scf_list.list.item(2).setSelected(True)
    setup.scf_list.remove_selected()
    assert reason(dialog) == "" and dialog.continue_button.isEnabled()


def test_add_opens_the_dialog_for_several_files(qtbot, dialog, monkeypatch):
    asked = []

    def choose(parent, start):
        asked.append(start)
        return [SI_SCF, AL_SCF]

    monkeypatch.setattr(scf_list, "choose_scfs", choose)
    dialog.setup.set_type(TYPE)
    dialog.setup.scf_list.add_button.click()
    qtbot.waitUntil(lambda: not dialog.setup.scf_list.reading)
    assert dialog.setup.scf_list.paths == [SI_SCF, AL_SCF] and dialog.continue_button.isEnabled()
    dialog.setup.scf_list.add_button.click()  # again: it opens where the last one is
    assert asked[1] == AL_SCF.parent


def test_a_type_of_one_scf_ignores_the_list(qtbot, dialog):
    setup = dialog.setup
    setup.set_type(TYPE)
    add_scfs(qtbot, dialog, [SI_SCF, AL_SCF])
    setup.set_type("scf")
    assert setup.scfs == () and setup.scf is None
    assert not dialog.continue_button.isEnabled()
    pick_scf(qtbot, dialog, NI_SCF)
    dialog.continue_button.click()
    assert [planned.name for planned in dialog.tabs.plan.files] == ["scf.qsub", "scf_ni.in"]


def test_closing_the_new_type_unedited_does_not_ask(qtbot, dialog, asked):
    dialog.setup.set_type(TYPE)
    add_scfs(qtbot, dialog, [SI_SCF, AL_SCF])
    dialog.continue_button.click()
    with qtbot.waitSignal(dialog.destroyed, timeout=2000):
        dialog.cancel_button.click()
    assert asked == []


def test_the_same_prefix_twice_keeps_create_off_until_one_is_edited(qtbot, dialog, tmp_path):
    """Two copies of one SCF would share ``./tmp/silicon.save``: their names differ by themselves, and
    "Criar" waits for a prefix changed by hand in the preview (spec 79)."""
    again = tmp_path / "si_again.scf.in"
    shutil.copyfile(SI_SCF, again)
    dialog.setup.set_type(TYPE)
    add_scfs(qtbot, dialog, [SI_SCF, again])
    dialog.continue_button.click()
    tabs = dialog.tabs
    assert tabs.tab_labels()[1:3] == ["SCF (scf_silicon.in)", "SCF (scf_silicon_2.in)"]
    same = SAME_PREFIX.format(prefix="silicon")
    assert tabs.blocking() == same and not dialog.create_button.isEnabled()
    preview = tabs.previews["scf1"]
    preview.setPlainText(preview.toPlainText().replace("prefix='silicon'", "prefix='silicon_b'"))
    assert tabs.blocking() == "" and dialog.create_button.isEnabled()
    tabs.restore("scf1")
    assert tabs.blocking() == same and not dialog.create_button.isEnabled()
