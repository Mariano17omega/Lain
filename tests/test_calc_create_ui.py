"""Spec 26 R1, R5: the "Criar cálculo" button, action and controller in the main window."""

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.calc_create.writer import CreateError, files_to_write
from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.ui import calc_create_controller
from qe_studio.ui.calc_create_controller import AVAILABLE_TIP, MISSING_ROOT_TIP
from qe_studio.ui.dialogs.calc_create import dialog as dialog_module

from calc_dialog_helpers import to_files, tree


@pytest.fixture(autouse=True)
def no_questions(monkeypatch):
    """A real discard question would block; the window closes without one here."""
    monkeypatch.setattr(dialog_module, "ask_discard", lambda parent: True)


def open_dialog(window):
    window.activity.new_calc.click()
    dialog = window.calc_create.dialog
    assert dialog is not None
    return dialog


def close(dialog) -> None:
    if not sip.isdeleted(dialog):
        dialog.close()


def menu_texts(window, title: str) -> list[str]:
    bar = window.menuBar()
    menu = next(a.menu() for a in bar.actions() if a.text() == title)
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_button_action_and_palette(qtbot, main_window):
    window = main_window
    button = window.activity.new_calc
    assert (button.text(), button.icon_name) == ("Criar", "add_circle")
    assert button.toolTip() == AVAILABLE_TIP and button.isEnabled()
    assert menu_texts(window, "Ferramentas")[0] == "Criar cálculo…"
    labels = [row.label for row in window.command_palette.rows_for(">criar")]
    assert "Criar cálculo…" in labels
    with qtbot.waitSignal(window.activity.create_requested):
        button.click()
    dialog = window.calc_create.dialog
    assert dialog is not None and dialog.isVisible()
    window._actions["calc.create"].trigger()  # one window at a time
    assert window.calc_create.dialog is dialog
    close(dialog)
    qtbot.waitUntil(lambda: window.calc_create.dialog is None, timeout=2000)


def test_disabled_without_a_project_folder(qtbot, window_factory, tmp_path, demo_project):
    config = parse_config({"paths": {"local_root": str(tmp_path / "sumiu")}})
    window = window_factory(LoadedConfig(config, None))
    button, action = window.activity.new_calc, window._actions["calc.create"]
    assert not button.isEnabled() and not action.isEnabled()
    assert button.toolTip() == MISSING_ROOT_TIP == action.toolTip()
    assert "Criar cálculo…" not in [r.label for r in window.command_palette.rows_for(">criar")]
    window.calc_create.open()
    assert window.calc_create.dialog is None
    window.use_session_root(demo_project)
    assert button.isEnabled() and action.isEnabled()
    assert button.toolTip() == AVAILABLE_TIP


def create(qtbot, window, **setup):
    """Fill the window, press "Criar", wait for the folder; the step 2 page and the result."""
    dialog = open_dialog(window)
    tabs = to_files(qtbot, dialog, **setup)
    with qtbot.waitSignal(window.calc_create.created, timeout=10_000) as blocker:
        dialog.create_button.click()
    return tabs, blocker.args[0]


def test_create_writes_the_plan_and_selects_the_folder(qtbot, main_window, demo_project):
    window = main_window
    dialog = open_dialog(window)
    tabs = to_files(qtbot, dialog, "pdos", location=demo_project)
    tabs.notes.setPlainText("PDOS do Al\n")
    expected = files_to_write(tabs.plan, tabs.notes_text())
    with qtbot.waitSignal(window.calc_create.created, timeout=10_000) as blocker:
        dialog.create_button.click()
    created = blocker.args[0]
    folder = demo_project / "pdos_Al"
    assert created.folder == folder
    assert sorted(p.name for p in folder.iterdir()) == sorted(f.name for f in expected)
    for planned in expected:
        assert (folder / planned.name).read_bytes() == planned.text.encode("utf-8")
    assert "descricao.md" in [f.name for f in expected]
    qtbot.waitUntil(lambda: window.calc_create.dialog is None, timeout=2000)
    assert window.current_folder() == folder
    notice = window.toast.current
    assert notice is not None and notice.level == "success"
    assert notice.text == "Pasta pdos_Al criada com 5 arquivos"
    assert "Enviar ao cluster" not in notice.text  # spec 27 adds it with its action


def test_the_same_name_twice_gets_a_number(qtbot, main_window, demo_project):
    window = main_window
    _tabs, first = create(qtbot, window, type_id="scf", location=demo_project)
    qtbot.waitUntil(lambda: window.calc_create.dialog is None, timeout=2000)
    tabs, second = create(qtbot, window, type_id="scf", location=demo_project)
    assert (first.folder.name, second.folder.name) == ("scf_Al", "scf_Al_1")
    assert second.renamed_from == "scf_Al"
    assert "descricao.md" not in [p.name for p in second.files]  # no notes, no file
    assert [p.name for p in second.files] == [f.name for f in tabs.plan.files]


def test_a_failure_keeps_the_window_and_writes_nothing(
    qtbot, main_window, demo_project, monkeypatch
):
    window = main_window
    errors = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text: errors.append((title, text))
    )

    def refuse(*_args):
        raise CreateError("Não foi possível criar a pasta pdos_Al: disco cheio")

    monkeypatch.setattr(calc_create_controller, "create_folder", refuse)
    before = tree(demo_project)
    dialog = open_dialog(window)
    to_files(qtbot, dialog, "pdos", location=demo_project)
    with qtbot.waitSignal(window.calc_create.failed, timeout=10_000):
        dialog.create_button.click()
    assert errors == [("Criar cálculo", "Não foi possível criar a pasta pdos_Al: disco cheio")]
    assert window.calc_create.dialog is dialog and dialog.isVisible()
    assert dialog.create_button.isEnabled() and dialog.pages.isEnabled()
    assert window.plot_workflow.busy.labels == []
    assert tree(demo_project) == before
    close(dialog)
