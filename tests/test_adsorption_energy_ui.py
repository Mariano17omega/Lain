"""Spec 78 R3: "Calcular adsorção…" in the grid's menu of several SCF outputs, and its window."""

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QMenu

from grid_helpers import menu_texts, select_names, show_folder
from qe_studio.ui.dialogs.adsorption_energy import AdsorptionEnergyDialog

from conftest import FIXTURES

ITEM = "Calcular adsorção…"
SOURCES = {"si": "si_bands", "al": "al_bands", "ni": "qe731_ni_spin_fixed"}


@pytest.fixture
def menus(monkeypatch):
    shown: list[QMenu] = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    return shown


@pytest.fixture
def ads_files(demo_project) -> Path:
    """A folder with three SCF runs, a bands output and a subfolder (before the window starts)."""
    folder = demo_project / "05_ads"
    folder.mkdir()
    for stem, source in SOURCES.items():
        for suffix in (".in", ".out"):
            shutil.copy(FIXTURES / source / f"{stem}.scf{suffix}", folder / f"{stem}.scf{suffix}")
    shutil.copy(FIXTURES / "si_bands/si.band.out", folder / "si.band.out")
    (folder / "sub").mkdir()
    return folder


@pytest.fixture
def ads(qtbot, ads_files, main_window) -> Path:
    """``ads_files`` listed in the grid. A test asks for ``ads_files`` before ``main_window``: the
    folder must exist when the window starts."""
    show_folder(qtbot, main_window, ads_files)
    return ads_files


def menu_of(window, menus, *names: str) -> QMenu:
    window._show_item_menu(select_names(window.files, *names), QPoint())
    return menus[-1]


def open_window(qtbot, window, menus, *names: str) -> AdsorptionEnergyDialog:
    action = next(a for a in menu_of(window, menus, *names).actions() if a.text() == ITEM)
    with qtbot.waitSignal(window.adsorption.opened, timeout=10_000) as blocker:
        action.trigger()
    dialog = blocker.args[0]
    assert isinstance(dialog, AdsorptionEnergyDialog)
    return dialog


def test_the_item_needs_two_scf_outputs(qtbot, ads_files, main_window, ads, menus):
    window = main_window
    window.service.detect_now(ads)
    assert ITEM in menu_texts(menu_of(window, menus, "al.scf.out", "ni.scf.out"))
    texts = menu_texts(menu_of(window, menus, "si.scf.out", "al.scf.out", "ni.scf.out"))
    assert texts.index(ITEM) == texts.index("Copiar") + 1
    for other in ("si.band.out", "si.scf.in", "sub"):
        assert ITEM not in menu_texts(menu_of(window, menus, "al.scf.out", "ni.scf.out", other))


def test_the_window_computes_and_saves(qtbot, ads_files, main_window, ads, menus):
    window = main_window
    window.service.detect_now(ads)
    dialog = open_window(qtbot, window, menus, "si.scf.out", "al.scf.out", "ni.scf.out")
    table = dialog.table
    names = [table.item(r, 1).text() for r in range(table.rowCount())]  # type: ignore[union-attr]
    assert names == ["silicon", "al", "nifix"]
    assert table.item(0, 0).text() == "Complexo"  # type: ignore[union-attr]
    assert dialog.equation.text() == "E_ads = E(silicon) - E(al) - E(nifix)"
    assert dialog.result_label.text().startswith("E_ads = 75.06454140 Ry = ")
    assert dialog.save_button.isEnabled()

    dialog.equation.setText("E_ads = 2* - E(nifix)")
    dialog.equation.setCursorPosition(len("E_ads = 2*"))
    button = next(b for b in dialog.variables if b.text() == "E(al)")
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert dialog.equation.text() == "E_ads = 2*E(al) - E(nifix)"
    assert dialog.save_button.isEnabled()

    dialog.equation.setText("")
    qtbot.keyClicks(dialog.equation, "E(al) -")
    assert dialog.error.text() == "Expressão incompleta" and dialog.error.isVisibleTo(dialog)
    assert not dialog.save_button.isEnabled()
    assert dialog.save_button.toolTip() == "Expressão incompleta"

    dialog.equation.setText("E_ads = E(silicon) - E(al) - E(nifix)")
    with qtbot.waitSignal(window.adsorption.saved, timeout=10_000) as blocker:
        qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    written = blocker.args[0]
    assert written == ads / "energia_ads_silicon_al_nifix.md"
    text = written.read_text()
    assert "| silicon | si.scf.out | 2 | -15.86827608 |" in text
    assert "E_ads = E(silicon) - E(al) - E(nifix)" in text
    toast = window.toast.current
    assert toast is not None and toast.text == "energia_ads_silicon_al_nifix.md criado"


def test_closing_the_main_window_closes_it(qtbot, ads_files, main_window, ads, menus):
    window = main_window
    window.service.detect_now(ads)
    dialog = open_window(qtbot, window, menus, "al.scf.out", "ni.scf.out")
    assert dialog.isVisible() and window.adsorption.dialogs == [dialog]
    with qtbot.waitSignal(dialog.destroyed, timeout=5000):
        window.close()
    assert window.adsorption.dialogs == []


class Undetected:
    """A detection service that has sniffed nothing yet."""

    def __init__(self):
        self.asked: list[Path] = []

    def file_sniff(self, path):
        return None

    def results(self, folder):
        self.asked.append(folder)


def test_an_output_not_detected_yet_asks_for_detection(qtbot, tmp_path):
    from PyQt6.QtWidgets import QWidget

    from qe_studio.ui.widgets.files.context_menu import ItemActions

    widget = QWidget()
    qtbot.addWidget(widget)
    service = Undetected()
    actions = ItemActions(widget, service)  # type: ignore[arg-type]
    assert not actions.scf_outputs([tmp_path / "a.out", tmp_path / "b.out"])
    assert service.asked == [tmp_path]  # once per folder
