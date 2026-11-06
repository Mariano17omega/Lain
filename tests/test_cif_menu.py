"""Spec 74 R2: "Gerar CIF" in the context menu of an SCF input."""

import shutil

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu, QMessageBox

from grid_helpers import menu_texts

from conftest import FIXTURES

ITEM = "Gerar CIF"


@pytest.fixture
def menus(monkeypatch):
    shown: list[QMenu] = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


@pytest.fixture
def si(demo_project):
    shutil.copytree(FIXTURES / "si_bands", demo_project / "05_si")
    return demo_project / "05_si"


def menu_of(window, path, menus) -> QMenu:
    window.service.detect_now(path.parent)
    window._show_item_menu([path], QPoint())
    return menus[-1]


def test_only_an_scf_input_has_the_item(main_window, si, menus):
    assert ITEM in menu_texts(menu_of(main_window, si / "si.scf.in", menus))
    for other in ("si.band.in", "si.scf.out"):
        assert ITEM not in menu_texts(menu_of(main_window, si / other, menus))
    assert ITEM not in menu_texts(menu_of(main_window, si, menus))
    window = main_window
    window._show_item_menu([si / "si.scf.in", si / "si.band.in"], QPoint())
    assert ITEM not in menu_texts(menus[-1])


def generate(qtbot, window, path, monkeypatch):
    monkeypatch.setattr(
        QMenu,
        "exec",
        lambda menu, pos: next(a for a in menu.actions() if a.text() == ITEM).trigger(),
    )
    window.service.detect_now(path.parent)
    with qtbot.waitSignal(window.derive.cif_generated, timeout=10_000) as blocker:
        window._show_item_menu([path], QPoint())
    return blocker.args[0]


def test_it_writes_beside_the_input_and_never_overwrites(qtbot, main_window, si, monkeypatch):
    first = generate(qtbot, main_window, si / "si.scf.in", monkeypatch)
    assert first == si / "si.scf.cif" and first.is_file()
    toast = main_window.toast.current
    assert toast is not None and toast.text == "si.scf.cif criado"
    second = generate(qtbot, main_window, si / "si.scf.in", monkeypatch)
    assert second == si / "si.scf_2.cif"


def test_an_unknown_label_warns_and_writes_nothing(qtbot, main_window, si, monkeypatch):
    path = si / "si.scf.in"
    path.write_text(path.read_text().replace("Si ", "X ").replace(" Si", " X"))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1:]))
    monkeypatch.setattr(
        QMenu,
        "exec",
        lambda menu, pos: next(a for a in menu.actions() if a.text() == ITEM).trigger(),
    )
    main_window.service.detect_now(si)
    with qtbot.waitSignal(main_window.derive.failed, timeout=10_000):
        main_window._show_item_menu([path], QPoint())
    assert warnings and warnings[0][0] == ITEM and "X" in warnings[0][1]
    assert not list(si.glob("*.cif"))
