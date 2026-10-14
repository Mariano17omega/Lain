"""Spec 46 R5: the "Print" button of the 3D window: the view as it is, at twice its pixels, saved without a
dialog as ``plots/<folders from the root>-<file>-3d.png``, never over another file."""

import copy
import shutil
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QImage

from qe_studio.ui.widgets.structure3d.overlay import HIGHLIGHT
from qe_studio.ui.widgets.structure3d.renderer import BACKGROUND
from qe_studio.ui.widgets.structure3d.window import PRINT_SCALE
from structure3d_helpers import (
    LEFT,
    SI_SCF,
    Windows,
    camera_state,
    click_atom,
    clickable_atom,
    empty_spot,
    make_structure,
    same_camera,
)

WAIT = 10_000


@pytest.fixture
def windows(qtbot, tmp_path):
    opened = Windows(qtbot, QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    yield opened
    opened.close_all()


@pytest.fixture
def folder(tmp_path):
    """A copy of the Si input: a window that prints writes ``plots/`` next to it, never in the fixtures."""
    target = tmp_path / "calculos" / "Analise_1"
    target.mkdir(parents=True)
    shutil.copy(SI_SCF, target / "si.scf.in")
    return target


def press(qtbot, window) -> Path:
    with qtbot.waitSignal(window.image_saved, timeout=WAIT) as saved:
        window.print_button.click()
    return saved.args[0]


def highlight_pixels(image: QImage) -> int:
    """How many pixels of the picture have exactly the color of the ring of the current atom."""
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    rgb = rows[:, : image.width(), 2::-1]  # memory order is B, G, R, A
    return int((rgb == HIGHLIGHT).all(axis=2).sum())


def test_the_button_is_in_the_bar_after_vista(windows):
    window = windows.open(SI_SCF)
    button = window.print_button
    assert button.text() == "Print" and not button.icon().isNull()
    assert button.toolTip() == "Salvar a imagem da vista em PNG, na pasta plots/ do cálculo"
    assert button.isEnabled()
    layout = window.reset_button.parent().layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]
    assert order == [window.reset_button, window.view_button, button]


def test_a_structure_without_a_file_cannot_print(windows):
    structure = make_structure([[5, 0, 0], [0, 5, 0], [0, 0, 5]], [[0, 0, 0]], ["Si"])
    window = windows.open(structure=structure)
    assert not window.print_button.isEnabled()


def test_print_saves_the_view_at_twice_its_size(qtbot, windows, folder):
    window = windows.open(folder / "si.scf.in")
    canvas = window.canvas
    target = press(qtbot, window)

    assert target == folder / "plots" / "Analise_1-si.scf-3d.png"
    image = QImage(str(target))
    assert not image.isNull()
    assert PRINT_SCALE == 2
    assert (image.width(), image.height()) == (canvas.width() * 2, canvas.height() * 2)
    assert image.pixelColor(0, 0).getRgb()[:3] == BACKGROUND[True]  # the scene's background
    assert window.statusBar().currentMessage() == "Imagem salva em plots/Analise_1-si.scf-3d.png"


def test_a_second_print_never_overwrites_the_first(qtbot, windows, folder):
    window = windows.open(folder / "si.scf.in")
    first = press(qtbot, window)
    before = first.read_bytes()
    window.canvas.rotate_structure("z")  # another view: another picture
    second = press(qtbot, window)
    assert second == folder / "plots" / "Analise_1-si.scf-3d_2.png"
    assert first.read_bytes() == before and second.read_bytes() != before
    third = press(qtbot, window)
    assert third.name == "Analise_1-si.scf-3d_3.png"


def test_two_quick_clicks_choose_two_names(qtbot, windows, folder):
    window = windows.open(folder / "si.scf.in")
    saved: list = []
    window.image_saved.connect(saved.append)
    window.print_button.click()
    window.print_button.click()
    qtbot.waitUntil(lambda: len(saved) == 2, timeout=WAIT)
    assert len(set(saved)) == 2 and all(p.exists() for p in saved)


def test_print_leaves_the_view_alone(qtbot, windows, folder):
    window = windows.open(folder / "si.scf.in")
    canvas = window.canvas
    ref = clickable_atom(canvas)
    click_atom(qtbot, canvas, ref)
    options, camera, marks = copy.deepcopy(canvas.options), camera_state(canvas), canvas.marks
    press(qtbot, window)
    canvas.grab()
    assert canvas.options == options and canvas.current == ref and canvas.marks == marks
    assert same_camera(camera_state(canvas), camera)
    assert canvas.draft is False


def test_the_name_carries_the_project_of_the_root(qtbot, windows, folder, tmp_path):
    root = tmp_path / "calculos"
    window = windows.open(folder / "si.scf.in", root=lambda: root)
    assert press(qtbot, window).name == "Analise_1-si.scf-3d.png"
    deep = folder / "nivel2"
    deep.mkdir()
    shutil.copy(SI_SCF, deep / "si.scf.in")
    other = windows.open(deep / "si.scf.in", root=lambda: root)
    assert press(qtbot, other) == deep / "plots" / "Analise_1-nivel2-si.scf-3d.png"
    # the root is asked at each click: another one changes the next name
    base = tmp_path
    moved = {"root": root}
    third = windows.open(folder / "si.scf.in", root=lambda: moved["root"])
    moved["root"] = base
    assert press(qtbot, third).name == "calculos-Analise_1-si.scf-3d.png"


def test_a_folder_that_is_gone_fails_with_a_message_and_is_not_recreated(qtbot, windows, folder):
    window = windows.open(folder / "si.scf.in")
    shutil.rmtree(folder)
    with qtbot.waitSignal(window.print_failed, timeout=WAIT) as failed:
        window.print_button.click()
    assert "pasta" in failed.args[0]
    assert window.statusBar().currentMessage().startswith("Não foi possível salvar a imagem: ")
    assert not folder.exists() and not folder.parent.joinpath("Analise_1").exists()


def test_the_ring_of_the_current_atom_is_in_the_picture_until_the_view_is_cleared(
    qtbot, windows, folder
):
    window = windows.open(folder / "si.scf.in")
    canvas = window.canvas
    assert highlight_pixels(QImage(str(press(qtbot, window)))) == 0  # no current atom
    click_atom(qtbot, canvas, clickable_atom(canvas))
    with_ring = QImage(str(press(qtbot, window)))
    assert highlight_pixels(with_ring) > 0
    qtbot.mouseClick(canvas, LEFT, pos=empty_spot(canvas))
    assert canvas.current is None
    assert highlight_pixels(QImage(str(press(qtbot, window)))) == 0
