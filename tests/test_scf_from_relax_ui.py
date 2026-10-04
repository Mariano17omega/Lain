"""Spec 24 R5: "Gerar SCF convergido" in the context menu, and what clicking it does."""

import dataclasses

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu, QMessageBox

from grid_helpers import menu_texts, names, show_folder
from qe_studio.core.qe.pw_input import parse_input
from qe_studio.core.qe.scf_from_relax import NO_INPUT

from conftest import FIXTURES

ITEM = "Gerar SCF convergido"


@pytest.fixture
def menus(monkeypatch):
    shown: list[QMenu] = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


def item(menu: QMenu):
    return next((a for a in menu.actions() if a.text() == ITEM), None)


def menu_of(window, path, menus) -> QMenu:
    window.service.detect_now(path.parent)  # fills the caches the menu reads
    window._show_item_menu([path], QPoint())
    return menus[-1]


def test_the_item_follows_resumo_for_a_converged_relax(main_window, demo_project, menus):
    menu = menu_of(main_window, demo_project / "01_relax/si.rel.out", menus)
    assert menu_texts(menu)[:2] == ["Resumo", ITEM]
    assert menu.actions()[2].isSeparator()
    action = item(menu)
    assert action is not None and action.isEnabled() and action.toolTip() == ITEM


@pytest.mark.parametrize(
    "rel", ["01_relax/si.rel.in", "02_scf/scf.out", "03_bands/bands.out", "04_pdos/nscf.out"]
)
def test_no_item_for_other_files(main_window, demo_project, menus, rel):
    assert item(menu_of(main_window, demo_project / rel, menus)) is None


@pytest.mark.parametrize(
    "old, new",
    [
        ("bfgs converged in   7 scf cycles and   6 bfgs steps", "bfgs failed after 7 scf cycles"),
        ("JOB DONE.", ""),
    ],
    ids=["bfgs_failed", "no_job_done"],
)
def test_no_item_for_a_relax_not_converged_or_not_finished(
    main_window, demo_project, menus, old, new
):
    output = demo_project / "01_relax/si.rel.out"
    output.write_text(output.read_text().replace(old, new))
    assert item(menu_of(main_window, output, menus)) is None


def test_no_item_when_the_tail_missed_the_marker(main_window, demo_project, menus, monkeypatch):
    output = demo_project / "01_relax/si.rel.out"
    window = main_window
    window.service.detect_now(output.parent)
    sniff = window.service.file_sniff(output)
    assert sniff is not None and sniff.pw is not None
    unknown = dataclasses.replace(sniff, pw=dataclasses.replace(sniff.pw, geometry_converged=None))
    real = window.service.file_sniff
    monkeypatch.setattr(window.service, "file_sniff", lambda p: unknown if p == output else real(p))
    window._show_item_menu([output], QPoint())
    assert item(menus[-1]) is None


def test_disabled_without_the_input_or_with_an_scf_input(main_window, demo_project, menus):
    folder = demo_project / "01_relax"
    (folder / "si.rel.in").unlink()
    menu = menu_of(main_window, folder / "si.rel.out", menus)
    action = item(menu)
    assert action is not None and not action.isEnabled()
    assert action.toolTip() == NO_INPUT and menu.toolTipsVisible()
    text = (FIXTURES / "si_relax/si.rel.in").read_text().replace("'relax'", "'scf'")
    (folder / "si.rel.in").write_text(text)
    action = item(menu_of(main_window, folder / "si.rel.out", menus))
    assert action is not None and not action.isEnabled()
    assert action.toolTip() == "si.rel.in não é um relax/vc-relax (calculation = 'scf')"


def generate(qtbot, window, output, monkeypatch, signal):
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: item(menu).trigger())
    window.service.detect_now(output.parent)
    with qtbot.waitSignal(signal, timeout=10_000) as blocker:
        window._show_item_menu([output], QPoint())
        assert "Gerando SCF convergido…" in window.plot_workflow.busy.labels
    assert window.plot_workflow.busy.labels == []
    return blocker.args[0]


def test_clicking_writes_the_scf_and_a_second_click_a_new_name(
    qtbot, main_window, demo_project, monkeypatch
):
    window = main_window
    folder = demo_project / "01_relax"
    show_folder(qtbot, window, folder)
    output = folder / "si.rel.out"
    path = generate(qtbot, window, output, monkeypatch, window.derive.generated)
    assert path == folder / "scf_convergido_silicon.in"
    assert parse_input(path.read_text()).calculation == "scf"
    toast = window.toast
    assert toast.current is not None and toast.current.level == "success"
    assert toast.current.text == "scf_convergido_silicon.in criado"
    assert str(path) in toast.current.details
    qtbot.waitUntil(lambda: "scf_convergido_silicon.in" in names(window.files), timeout=5000)
    again = generate(qtbot, window, output, monkeypatch, window.derive.generated)
    assert again == folder / "scf_convergido_silicon_1.in"
    assert path.read_bytes() == again.read_bytes()


def test_a_failure_warns_and_writes_nothing(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    folder = demo_project / "01_relax"
    source = folder / "si.rel.in"
    source.write_text(source.read_text().replace("nat=  2", "nat=  3"))
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warned.append(a[2])))
    reason = generate(qtbot, window, folder / "si.rel.out", monkeypatch, window.derive.failed)
    assert reason == "nat = 3 no input, 2 posições na saída" and warned == [reason]
    assert sorted(p.name for p in folder.iterdir()) == ["si.rel.in", "si.rel.out"]
