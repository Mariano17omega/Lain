"""Spec 43 R4: "Visualização 3D" in the context menu of pw.x inputs, a new window per click with its
own settings, and the windows closed with the main one."""

import shutil

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu

from conftest import FIXTURES

ITEM = "Visualização 3D"
XCRYSDEN = "Abrir com XCrysDen"  # spec 45: next to it, disabled without paths.xcrysden_path
MENU = ["Abrir local de origem", "Abrir com", "Copiar", "Renomear"]


@pytest.fixture
def si_folder(demo_project):
    folder = demo_project / "05_si"
    shutil.copytree(FIXTURES / "si_bands", folder)
    return folder


def texts(menu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def menu_of(window, monkeypatch, *paths) -> QMenu:
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, pos: shown.append(menu))
    window._show_item_menu(list(paths), QPoint())
    return shown[-1]


def open_from_menu(qtbot, window, monkeypatch, path):
    def trigger(menu, pos):
        next(a for a in menu.actions() if a.text() == ITEM).trigger()

    monkeypatch.setattr(QMenu, "exec", trigger)
    with qtbot.waitSignal(window.structure3d.opened, timeout=10_000) as blocker:
        window._show_item_menu([path], QPoint())
    return blocker.args[0]


@pytest.fixture
def closing(main_window):
    """Closes every 3D window the test leaves open (the main window's teardown does too)."""
    yield main_window
    main_window.structure3d.close_dialog()


def test_the_item_is_only_in_pw_inputs(main_window, si_folder, monkeypatch):
    window = main_window
    window.service.detect_now(si_folder)  # the sniffs the menu reads
    scf = menu_of(window, monkeypatch, si_folder / "si.scf.in")
    assert texts(scf) == [ITEM, XCRYSDEN, *MENU]
    assert scf.actions()[2].isSeparator()
    bands = menu_of(window, monkeypatch, si_folder / "si.band.in")  # pw.x, calculation = 'bands'
    assert texts(bands) == [ITEM, XCRYSDEN, *MENU]
    for path in (si_folder / "si.scf.out", si_folder / "bands.in"):  # an output, a bands.x input
        assert ITEM not in texts(menu_of(window, monkeypatch, path)), path.name
    assert ITEM not in texts(menu_of(window, monkeypatch, si_folder))
    two = menu_of(window, monkeypatch, si_folder / "si.scf.in", si_folder / "si.band.in")
    assert ITEM not in texts(two)


def test_the_item_comes_after_resumo_and_before_the_converged_scf(main_window, si_folder):
    menu = main_window.item_actions.menu(
        si_folder / "si.scf.in", summary=True, structure=True, scf=""
    )
    assert texts(menu)[:3] == ["Resumo", ITEM, "Gerar SCF convergido"]
    assert menu.actions()[3].isSeparator()


def test_an_unsniffed_input_has_no_item_and_asks_for_detection(main_window, si_folder, monkeypatch):
    requested = []
    monkeypatch.setattr(main_window.service, "file_sniff", lambda path: None)
    monkeypatch.setattr(main_window.service, "results", lambda folder: requested.append(folder))
    assert texts(menu_of(main_window, monkeypatch, si_folder / "si.scf.in")) == MENU
    assert requested == [si_folder]


def test_the_item_opens_a_window(qtbot, closing, si_folder, monkeypatch):
    window = closing
    window.service.detect_now(si_folder)
    view = open_from_menu(qtbot, window, monkeypatch, si_folder / "si.scf.in")
    assert view.windowTitle() == "si.scf.in — 05_si · Visualização 3D"
    assert view.info.text() == "si.scf.in · Si2 · nat = 2 · ibrav = 2"
    assert view.parent() is None and view.isVisible()
    assert view.width() == 1280 and view.height() == 820
    assert window.structure3d.windows == [view]
    assert view.canvas.options.background == "escuro"  # the app theme when it opened


def test_each_click_is_a_window_with_its_own_settings(qtbot, closing, si_folder, monkeypatch):
    window = closing
    window.service.detect_now(si_folder)
    first = open_from_menu(qtbot, window, monkeypatch, si_folder / "si.scf.in")
    second = open_from_menu(qtbot, window, monkeypatch, si_folder / "si.scf.in")
    assert first is not second and window.structure3d.windows == [first, second]
    zoom = second.canvas.camera.zoom
    first.panel.radius.setValue(2.0)
    first.panel.swatches[0].color_changed.emit("#ff00ff")
    first.canvas.camera.zoom *= 3
    assert second.canvas.options.radius_scale == 1.0
    assert second.canvas.options.species_colors == {}
    assert second.canvas.camera.zoom == pytest.approx(zoom)
    assert second.panel.radius.value() == 1.0


def test_a_file_that_cannot_be_read_gives_a_toast_and_no_window(
    qtbot, closing, tmp_path, monkeypatch
):
    window = closing
    broken = tmp_path / "quebrado.in"
    broken.write_text(
        (FIXTURES / "si_bands" / "si.scf.in").read_text().split("ATOMIC_POSITIONS")[0]
    )
    toasts = []
    monkeypatch.setattr(window.toast, "show_message", lambda *args: toasts.append(args))
    with qtbot.waitSignal(window.structure3d.failed, timeout=10_000) as blocker:
        window.structure3d.open(broken)
    message = (
        "Visualização 3D de quebrado.in: Estrutura de quebrado.in ilegível: sem ATOMIC_POSITIONS"
    )
    assert blocker.args == [message]
    assert toasts == [(message, "warning")]
    assert window.structure3d.windows == []


def test_closing_a_window_drops_it(qtbot, closing, si_folder):
    controller = closing.structure3d
    with qtbot.waitSignal(controller.opened, timeout=10_000) as blocker:
        controller.open(si_folder / "si.scf.in")
        assert closing.status.busy.text().startswith("Lendo estrutura…")  # the footer spinner
    assert closing.status.busy.isHidden()
    blocker.args[0].close()
    assert controller.windows == []


def test_closing_the_main_window_closes_them_all(qtbot, main_window, si_folder):
    controller = main_window.structure3d
    opened = []
    for _ in range(2):
        with qtbot.waitSignal(controller.opened, timeout=10_000) as blocker:
            controller.open(si_folder / "si.scf.in")
        opened.append(blocker.args[0])
    assert controller.close_dialog() is True
    assert controller.windows == []
    assert all(sip.isdeleted(w) or not w.isVisible() for w in opened)
    with qtbot.waitSignal(controller.opened, timeout=10_000) as blocker:
        controller.open(si_folder / "si.scf.in")
    main_window.close()
    assert controller.windows == []
