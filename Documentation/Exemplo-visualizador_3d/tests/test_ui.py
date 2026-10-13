import numpy as np
import pytest
from conftest import SAMPLES
from helpers import make_structure
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from viewer3d.core import measure
from viewer3d.core.structure import AtomRef
from viewer3d.ui.main_window import MainWindow

LEFT = Qt.MouseButton.LeftButton


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[1:]))
    return shown


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1100, 720)
    w.show()
    qtbot.waitExposed(w)
    return w


@pytest.fixture
def opened(window):
    assert window.open_path(SAMPLES / "scf.in")
    window.canvas.grab()  # paint once so picking data exists
    return window


def image_bytes(widget):
    image = widget.grab().toImage()
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    return bytes(ptr)


def click_atom(qtbot, canvas, ref, modifier=Qt.KeyboardModifier.NoModifier):
    canvas.grab()
    x, y = canvas.renderer.screen_position(ref)
    qtbot.mouseClick(canvas, LEFT, modifier, QPoint(round(x), round(y)))


def nearest_front_pair(canvas):
    """Two real atoms whose discs do not overlap on screen (so clicks are unambiguous)."""
    canvas.grab()
    order = canvas.renderer._pick_order.tolist()
    xy = canvas.renderer._pick_xy
    picked = []
    for i in order:
        if all(np.hypot(*(xy[i] - xy[j])) > 30 for j in picked):
            picked.append(i)
        if len(picked) == 2:
            break
    return [canvas.scene.refs[i] for i in picked]


def test_open_sample_fills_panels_and_status(opened):
    s = opened.canvas.structure
    assert "CH18Al8HgO36Si8" in opened._info.text()
    assert "nat = 72" in opened._info.text() and "ibrav = 0" in opened._info.text()
    assert opened._warning.text() == ""
    cell = opened.panel.cell._values
    assert float(cell["volume"].text()) == pytest.approx(s.volume, abs=1e-3)
    assert cell["nat"].text() == "72"
    assert opened.panel.display.species.rowCount() == 6
    image = opened.canvas.grab().toImage()
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    assert len(np.unique(np.frombuffer(ptr, np.uint8).reshape(-1, 4), axis=0)) > 20


def test_click_selects_atom_and_atom_tab_shows_number_and_neighbours(qtbot, opened):
    canvas = opened.canvas
    ref = AtomRef(opened.canvas.structure.symbols.index("Hg"))
    click_atom(qtbot, canvas, ref)
    assert canvas.selection == [ref]
    atom = opened.panel.atom
    assert atom._rows["number"][1].text() == str(ref.index + 1)
    near = canvas.graph.neighbors(ref)
    assert atom._rows["coordination"][1].text() == str(len(near))
    assert atom._table.rowCount() == len(near)
    assert atom._table.item(0, 2).text() == f"{near[0][1]:.4f}"


def test_two_clicks_give_the_core_distance(qtbot, opened):
    canvas = opened.canvas
    a, b = nearest_front_pair(canvas)
    click_atom(qtbot, canvas, a)
    click_atom(qtbot, canvas, b)
    assert canvas.selection == [a, b]
    expected = measure.distance(canvas.structure, a, b).value
    row = opened.panel.measures._rows[-1]
    assert row[0].startswith("Distância")
    assert float(row[2]) == pytest.approx(expected, abs=5e-5)


def test_ctrl_click_toggles_and_empty_click_clears(qtbot, opened):
    canvas = opened.canvas
    a, b = nearest_front_pair(canvas)
    click_atom(qtbot, canvas, a)
    click_atom(qtbot, canvas, b, Qt.KeyboardModifier.ControlModifier)
    assert canvas.selection == [a, b]
    click_atom(qtbot, canvas, b, Qt.KeyboardModifier.ControlModifier)
    assert canvas.selection == [a]
    qtbot.mouseClick(canvas, LEFT, Qt.KeyboardModifier.NoModifier, QPoint(3, 3))
    assert canvas.selection == []
    assert opened.panel.atom._placeholder.isVisible()


def test_neighbour_row_click_selects_that_neighbour(qtbot, opened):
    canvas = opened.canvas
    ref = AtomRef(opened.canvas.structure.symbols.index("C"))
    click_atom(qtbot, canvas, ref)
    first = canvas.graph.neighbors(ref)[0][0]
    opened.panel.atom._row_clicked(0, 0)
    assert canvas.selection[-1] == first
    assert opened.panel.atom._rows["number"][1].text() == str(first.index + 1)


def test_nearest_image_button(opened):
    canvas = opened.canvas
    far = AtomRef(1, (3, -2, 1))
    canvas.set_selection([AtomRef(0), far])
    opened.panel.measures.use_nearest_image()
    best = measure.nearest_image(canvas.structure, AtomRef(0), far)
    assert canvas.selection[1] == best
    assert best != far


def test_repeat_2x1x1_doubles_drawn_atoms(opened):
    canvas = opened.canvas
    canvas.grab()
    one = canvas.stats.atoms
    opened.panel.display.reps[0].setValue(2)
    canvas.grab()
    assert canvas.stats.atoms == 2 * one
    assert canvas.stats.ghosts > 0


def test_drag_rotates_and_r_restores(qtbot, opened):
    canvas = opened.canvas
    before = image_bytes(canvas)
    qtbot.mousePress(canvas, LEFT, pos=QPoint(400, 300))
    qtbot.mouseMove(canvas, QPoint(470, 330))
    qtbot.mouseMove(canvas, QPoint(520, 360))
    qtbot.mouseRelease(canvas, LEFT, pos=QPoint(520, 360))
    rotated = image_bytes(canvas)
    assert rotated != before
    assert canvas.selection == []  # a drag is not a click
    qtbot.keyClick(canvas, Qt.Key.Key_R)
    assert image_bytes(canvas) == before


def test_double_click_resets_view(qtbot, opened):
    canvas = opened.canvas
    before = image_bytes(canvas)
    canvas.camera.pan_by(50, 30)
    canvas.update()
    assert image_bytes(canvas) != before
    qtbot.mouseDClick(canvas, LEFT, pos=QPoint(10, 10))
    assert image_bytes(canvas) == before


def test_wheel_zooms_towards_the_pointer(opened):
    canvas = opened.canvas
    zoom = canvas.camera.zoom
    event = QWheelEvent(
        QPointF(300, 200),
        QPointF(300, 200),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas, event)
    assert canvas.camera.zoom > zoom


def test_keys_p_and_abc(qtbot, opened):
    canvas = opened.canvas
    assert canvas.options.perspective
    qtbot.keyClick(canvas, Qt.Key.Key_P)
    assert not canvas.options.perspective
    assert not opened.panel.display.perspective.isChecked()
    before = canvas.camera.rotation.copy()
    qtbot.keyClick(canvas, Qt.Key.Key_C)
    assert not np.allclose(canvas.camera.rotation, before)
    # looking along c: the third lattice vector points at the viewer
    c = canvas.structure.cell[2]
    assert canvas.camera.rotation[2] @ c == pytest.approx(np.linalg.norm(c))
    qtbot.keyClick(canvas, Qt.Key.Key_Plus)
    qtbot.keyClick(canvas, Qt.Key.Key_Minus)


def test_hover_reports_atom_in_status_bar(qtbot, opened):
    canvas = opened.canvas
    ref = AtomRef(opened.canvas.structure.symbols.index("Hg"))
    canvas.grab()
    x, y = canvas.renderer.screen_position(ref)
    with qtbot.waitSignal(canvas.hovered, timeout=2000):
        qtbot.mouseMove(canvas, QPoint(round(x), round(y)))
    assert opened._hover.text() == f"#{ref.index + 1} Hg"
    qtbot.mouseMove(canvas, QPoint(2, 2))
    assert opened._hover.text() == ""


def test_read_error_is_reported_in_portuguese(opened, no_modal_dialogs, tmp_path):
    bad = tmp_path / "bad.in"
    bad.write_text("&system\n ibrav = 1\n/\n")
    assert opened.open_path(bad) is False
    assert "celldm(1)" in opened.last_error or "nat" in opened.last_error
    assert no_modal_dialogs
    assert opened.open_path(tmp_path / "missing.in") is False
    assert "não encontrado" in opened.last_error
    assert "Erro" in opened.statusBar().currentMessage()
    assert opened.canvas.structure is not None  # the previous structure stays on screen


def test_warnings_show_icon_and_tooltip(window, tmp_path):
    f = tmp_path / "w.in"
    f.write_text("&system\nibrav=1, celldm(1)=10, nat=1\n/\nATOMIC_POSITIONS\nSi 0 0 0\n")
    assert window.open_path(f)
    assert window._warning.text() == "⚠"
    assert "alat" in window._warning.toolTip()


def test_species_visibility_and_color(opened):
    display, canvas = opened.panel.display, opened.canvas
    canvas.grab()
    all_atoms = canvas.stats.atoms
    box = display.species.cellWidget(3, 2).layout().itemAt(0).widget()  # H
    box.setChecked(False)
    canvas.grab()
    assert canvas.stats.atoms == all_atoms - 18
    display.set_species_color(2, (10, 200, 30))
    assert canvas.options.species_colors[2] == (10, 200, 30)
    canvas.grab()


def test_draft_mode_during_interaction_then_full_quality(qtbot, window):
    n = 8
    grid = np.array([(i, j, k) for i in range(n) for j in range(n) for k in range(n)], float)
    s = make_structure(1.5 * n * np.eye(3), grid / n, ["C"] * len(grid))
    window.show_structure(s)
    canvas = window.canvas
    assert canvas._primitive_estimate() > 1500
    canvas.grab()
    assert canvas.stats.draft is False
    qtbot.mousePress(canvas, LEFT, pos=QPoint(300, 300))
    qtbot.mouseMove(canvas, QPoint(340, 320))
    qtbot.mouseMove(canvas, QPoint(380, 340))
    assert canvas.draft is True
    canvas.grab()
    assert canvas.stats.draft is True
    qtbot.mouseRelease(canvas, LEFT, pos=QPoint(380, 340))
    qtbot.waitUntil(lambda: canvas.draft is False, timeout=2000)
    canvas.grab()
    assert canvas.stats.draft is False


def test_small_scene_never_uses_draft(qtbot, opened):
    qtbot.mousePress(opened.canvas, LEFT, pos=QPoint(400, 300))
    qtbot.mouseMove(opened.canvas, QPoint(450, 330))
    assert opened.canvas.draft is False


def test_high_dpi_render_has_device_pixels(opened):
    from PyQt6.QtCore import QSize

    image = opened.canvas.render_image(QSize(200, 150), dpr=2.0)
    assert (image.width(), image.height()) == (400, 300)
    assert image.devicePixelRatio() == 2.0


def test_drop_event_opens_file(qtbot, window):
    from PyQt6.QtCore import QMimeData, QUrl
    from PyQt6.QtGui import QDropEvent

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(SAMPLES / "scf.in"))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert window.canvas.structure is not None and len(window.canvas.structure) == 72
