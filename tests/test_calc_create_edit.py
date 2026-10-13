"""Spec 39 R2: the files of "Criar cálculo" edited in their preview, in the "avancado" mode only.

The typed text wins over the fields, is marked "editado" (tab, "Arquivos", a bar over the preview),
is checked as typed without blocking "Criar", and goes into the ``CreateRequest``.
"""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor

from qe_studio.core.calc_create.preview import EDITED_MARK
from qe_studio.ui.dialogs.calc_create import CalcCreateDialog
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module
from qe_studio.ui.dialogs.calc_create.setup_page import REBUILD_EDITS_NOTE, REBUILD_NOTE
from qe_studio.ui.theme.manager import ThemeManager

from calc_dialog_helpers import pick_scf, to_files, type_in_preview
from calc_helpers import JOBS, SI_SCF

NOTE = "! nota"


@pytest.fixture
def make_dialog(qtbot, tmp_path):
    """Windows on a folder of ``tmp_path``, closed at teardown unless a test closed them."""
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
def asked(monkeypatch):
    """The discard question, answered yes; its calls."""
    calls = []

    def ask(parent):
        calls.append(parent)
        return True

    monkeypatch.setattr(dialog_module, "ask_discard", ask)
    return calls


def edited_scf(qtbot, dialog, type_id="pdos"):
    tabs = to_files(qtbot, dialog, type_id)
    type_in_preview(qtbot, tabs, "scf", NOTE)
    return tabs


def test_the_standard_mode_cannot_edit(qtbot, make_dialog):
    dialog = make_dialog(mode="padrao")
    tabs = to_files(qtbot, dialog, "pdos")
    before = tabs.previews["scf"].toPlainText()
    type_in_preview(qtbot, tabs, "scf", NOTE)
    assert tabs.previews["scf"].toPlainText() == before
    assert not tabs.has_edits and not tabs.dirty
    assert tabs.files_view.isEnabled() and tabs.notes.isReadOnly() is False  # "Descrição" stays


def test_typing_edits_the_file_and_the_request(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = edited_scf(qtbot, dialog)
    scf = tabs.plan.by_key("scf")
    assert scf is not None and scf.text.endswith(f"\n{NOTE}\n")  # with the final newline
    assert tabs.edited_keys() == ["scf"] and tabs.dirty
    assert f"SCF (scf_al.in){EDITED_MARK}" in tabs.tab_labels()
    assert not tabs.edit_bars["scf"].isHidden() and tabs.edit_bars["nscf"].isHidden()
    kinds = {
        tabs.files_view.tree.topLevelItem(i).text(0): tabs.files_view.tree.topLevelItem(i).text(1)
        for i in range(tabs.files_view.tree.topLevelItemCount())
    }
    assert kinds["scf_al.in"] == f"Input do pw.x{EDITED_MARK}"
    assert kinds["nscf_al.in"] == "Input do pw.x"
    with qtbot.waitSignal(dialog.create_requested) as blocker:
        dialog.create_button.click()
    request = blocker.args[0]
    assert request.plan == tabs.plan
    assert request.plan.by_key("scf").text == scf.text


def test_a_field_change_keeps_the_edit_and_restore_brings_the_fields_back(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = to_files(qtbot, dialog, "pdos")
    script = tabs.previews["script"]
    type_in_preview(qtbot, tabs, "script", "# meu")
    typed = script.toPlainText()
    np_ = tabs.widget_of("np")
    np_.setText("")
    qtbot.keyClicks(np_, "8")
    nbnd = tabs.widget_of("nbnd")
    nbnd.setText("")
    qtbot.keyClicks(nbnd, "42")
    assert script.toPlainText() == typed  # the edit wins
    assert tabs.plan.by_key("script").text == typed + "\n"  # written with a final newline
    assert "nbnd = 42" in tabs.previews["nscf"].toPlainText()  # the other files follow the fields
    tabs.edit_bars["script"].restore_button.click()
    assert not tabs.has_edits and tabs.edit_bars["script"].isHidden()
    lines = script.toPlainText().splitlines()
    assert "# meu" not in lines and "#$ -pe physica 8" in lines  # the fields again
    assert tabs.plan.by_key("script").text == script.toPlainText()
    assert EDITED_MARK not in "".join(tabs.tab_labels())


def test_typing_back_the_generated_text_is_no_edit(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = to_files(qtbot, dialog, "pdos")
    generated = tabs.plan.by_key("scf").text
    type_in_preview(qtbot, tabs, "scf", "x")
    assert tabs.has_edits
    qtbot.keyClick(tabs.previews["scf"], Qt.Key.Key_Backspace)
    assert not tabs.has_edits and not tabs.dirty
    assert tabs.plan.by_key("scf").text == generated and tabs.edit_bars["scf"].isHidden()


def test_renaming_the_file_keeps_its_edit(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = edited_scf(qtbot, dialog)
    name = tabs.widget_of("name:scf")
    name.setText("")
    qtbot.keyClicks(name, "scf_teste.in")
    scf = tabs.plan.by_key("scf")
    assert scf is not None and scf.name == "scf_teste.in" and scf.text.endswith(f"{NOTE}\n")
    assert f"SCF (scf_teste.in){EDITED_MARK}" in tabs.tab_labels()
    assert '-i "scf_teste.in"' in tabs.previews["script"].toPlainText()


def test_back_and_continue_keep_the_edits(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = edited_scf(qtbot, dialog)
    dialog.back_button.click()
    assert dialog.setup.rebuild_note.isHidden()
    dialog.continue_button.click()
    assert dialog.tabs is tabs and tabs.edited_keys() == ["scf"]


def test_another_scf_drops_the_edits_and_says_so(qtbot, make_dialog):
    dialog = make_dialog()
    edited_scf(qtbot, dialog)
    dialog.back_button.click()
    pick_scf(qtbot, dialog, SI_SCF)
    assert dialog.setup.rebuild_note.text() == REBUILD_EDITS_NOTE
    dialog.continue_button.click()
    assert not dialog.tabs.has_edits and NOTE not in dialog.tabs.previews["scf"].toPlainText()
    dialog.back_button.click()
    dialog.setup.set_type("scf")
    assert dialog.setup.rebuild_note.text() == REBUILD_NOTE  # nothing edited to lose


def test_edits_stay_in_the_standard_mode(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = edited_scf(qtbot, dialog)
    dialog.mode_switch.buttons["padrao"].click()
    preview = tabs.previews["scf"]
    assert preview.isReadOnly() and preview.toPlainText().endswith(NOTE)
    assert not tabs.edit_bars["scf"].isHidden() and tabs.edited_keys() == ["scf"]
    tabs.edit_bars["scf"].restore_button.click()  # the way back works in either mode
    assert not tabs.has_edits and NOTE not in preview.toPlainText()


def test_closing_with_an_edit_asks(qtbot, make_dialog, asked):
    dialog = make_dialog()
    edited_scf(qtbot, dialog)
    dialog.close()
    assert asked == [dialog]


def test_write_problems_are_marked_and_never_block(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = to_files(qtbot, dialog, "pdos")
    preview = tabs.previews["scf"]
    tabs.tabs.setCurrentWidget(tabs._tab_of["scf"])
    text = preview.toPlainText()
    cursor = QTextCursor(preview.text_document())
    cursor.setPosition(text.index("=", text.index("calculation")))
    preview.setTextCursor(cursor)
    qtbot.keyClick(preview, Qt.Key.Key_Delete)  # calculation 'scf'
    line = next(
        i for i, row in enumerate(preview.toPlainText().splitlines()) if "calculation" in row
    )
    assert line in preview.diagnostics
    assert line in preview.highlighter._issues
    assert line in preview.changed_rows()  # the row now differs from the SCF
    assert dialog.create_button.isEnabled()
    tabs.edit_bars["scf"].restore_button.click()
    assert preview.diagnostics == {} and not preview.highlighter._issues


def test_the_script_is_checked_too(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = to_files(qtbot, dialog, "pdos")
    type_in_preview(qtbot, tabs, "script", "if true; then")
    script = tabs.previews["script"]
    assert script.diagnostics and dialog.create_button.isEnabled()


def test_the_check_waits_for_the_typing(qtbot, make_dialog):
    dialog = make_dialog()
    tabs = to_files(qtbot, dialog, "pdos")
    tabs.debounce_ms = 50
    type_in_preview(qtbot, tabs, "script", "if true; then")
    script = tabs.previews["script"]
    assert tabs.has_edits and not script.diagnostics  # the edit at once, the check 50 ms later
    qtbot.waitUntil(lambda: bool(script.diagnostics), timeout=2000)
