"""Shared pieces of the 3D viewer tests (spec 43): the fixture inputs, structures built from arrays and a
water-like molecule, plus a window of the viewer opened on a fixture (closed explicitly: delete-on-close),
and the gestures the tests make on its view."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

from qe_studio.core.structure3d.model import SourceInfo, SpeciesInfo, Structure
from qe_studio.core.structure3d.source import read_structure, structure_of_text  # noqa: F401

from conftest import FIXTURES

KAO = FIXTURES / "kao_surface_inputs"
SI_SCF = FIXTURES / "si_bands" / "si.scf.in"
NI_SCF = FIXTURES / "qe731_ni_spin_bands" / "ni.scf.in"
SLAB_2X1 = KAO / "scf-kaolinite-slab-001-2x1x1.in"
MOLECULE = KAO / "scf-H3CHg.in"
BULK = KAO / "scf-kaolinite.in"
# Every pw.x input of the fixtures (spec 43 R1.3).
PW_INPUTS = [
    FIXTURES / "al_bands" / "al.scf.in",
    FIXTURES / "al_bands" / "al.band.in",
    FIXTURES / "al_pdos_flat" / "al.nscf.in",
    SI_SCF,
    FIXTURES / "si_relax" / "si.rel.in",
    NI_SCF,
    FIXTURES / "kao_vc_relax" / "vc-relax.in",
    *sorted(KAO.glob("*.in")),
]

# Water-like: O in the middle of a 20 bohr cube, two H at 0.96 Å in the xy plane.
WATER = """&CONTROL
/
&SYSTEM
  ibrav = 1, celldm(1) = 20.0, nat = 3, ntyp = 2
/
ATOMIC_SPECIES
O 15.999 O.UPF
H 1.008 H.UPF
ATOMIC_POSITIONS angstrom
O 5.2917721 5.2917721 5.2917721
H 6.2517721 5.2917721 5.2917721
H 5.0514073 6.2211938 5.2917721
"""


def water() -> Structure:
    return structure_of_text(WATER, Path("agua.in"))


def si() -> Structure:
    return read_structure(SI_SCF)


def make_structure(cell, frac, labels) -> Structure:
    """A structure straight from arrays (one species per distinct label)."""
    unique = list(dict.fromkeys(labels))
    species = tuple(SpeciesInfo(label, None, None, i + 1) for i, label in enumerate(unique))
    return Structure(
        np.asarray(cell, dtype=float),
        tuple(labels),
        np.asarray(frac, dtype=float),
        (None,) * len(labels),
        species,
        SourceInfo(nat=len(labels)),
    )


# -- a window of the viewer and the gestures on its view ----------------------------------------

LEFT = Qt.MouseButton.LeftButton


class Windows:
    """Opens ``StructureWindow``s on fixtures and closes the ones still open at the end (they delete
    themselves on close: never ``qtbot.addWidget``)."""

    def __init__(self, qtbot, settings=None):
        from qe_studio.ui.theme.manager import ThemeManager

        self.qtbot, self.settings = qtbot, settings
        self.theme = ThemeManager("dark")
        self.opened: list = []

    def open(self, path: Path = SI_SCF, structure: Structure | None = None, **options):
        """``options`` go to ``StructureWindow`` (``root=``, spec 46)."""
        from qe_studio.ui.widgets.structure3d.window import StructureWindow

        window = StructureWindow(
            structure or read_structure(path), self.theme, self.settings, **options
        )
        window.show()
        self.qtbot.waitExposed(window)
        window.canvas.grab()  # one frame: the picking data exists
        self.opened.append(window)
        return window

    def close_all(self) -> None:
        for window in self.opened:
            if not sip.isdeleted(window):
                window.close()


def close_view(qtbot, main_window, view) -> None:
    """Close a 3D window of ``main_window`` and wait for its view: ``view3d.plot`` is written in the
    controller's save queue, and the toast of a failed write comes back after it (spec 47 R3)."""
    controller = main_window.structure3d
    view.close()
    qtbot.waitUntil(lambda: not controller.saving, timeout=10_000)


def camera_state(canvas) -> tuple:
    camera = canvas.camera
    return float(camera.zoom), camera.pan.copy(), camera.rotation.copy()


def same_camera(a: tuple, b: tuple) -> bool:
    return a[0] == pytest.approx(b[0]) and np.allclose(a[1], b[1]) and np.allclose(a[2], b[2])


def screen_of(canvas, ref) -> QPoint:
    canvas.grab()
    position = canvas.renderer.screen_position(ref)
    assert position is not None, ref
    return QPoint(round(position[0]), round(position[1]))


def clickable_atom(canvas):
    """A drawn atom whose disc is the frontmost under its center (a click there picks it)."""
    canvas.grab()
    renderer = canvas.renderer
    for index in renderer._pick_order.tolist():
        ref = canvas.scene.refs[index]
        x, y = renderer.screen_position(ref)
        if renderer.pick((round(x), round(y))) == ref and 30 < x < canvas.width() - 30:
            return ref
    raise AssertionError("no clickable atom")


def clickable_atoms(canvas, count: int, apart: float = 25.0) -> list:
    """``count`` drawn atoms each frontmost under its center and ``apart`` px from the others."""
    canvas.grab()
    renderer = canvas.renderer
    found, spots = [], []
    for index in renderer._pick_order.tolist():
        ref = canvas.scene.refs[index]
        x, y = renderer.screen_position(ref)
        inside = 20 < x < canvas.width() - 20 and 20 < y < canvas.height() - 20
        far = all(np.hypot(x - sx, y - sy) > apart for sx, sy in spots)
        if inside and far and renderer.pick((round(x), round(y))) == ref:
            found.append(ref)
            spots.append((x, y))
        if len(found) == count:
            return found
    raise AssertionError(f"only {len(found)} clickable atoms")


def click_atom(qtbot, canvas, ref, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    qtbot.mouseClick(canvas, LEFT, modifier, screen_of(canvas, ref))


def empty_spot(canvas) -> QPoint:
    """A point of the view with no atom under it."""
    canvas.grab()
    for x in range(5, canvas.width(), 15):
        for y in range(5, canvas.height(), 15):
            if canvas.renderer.pick((x, y)) is None:
                return QPoint(x, y)
    raise AssertionError("no empty spot")


def wheel(canvas, steps: int = 1, at: QPointF | None = None) -> None:
    at = at if at is not None else QPointF(canvas.width() / 3, canvas.height() / 3)
    event = QWheelEvent(
        at,
        at,
        QPoint(0, 0),
        QPoint(0, 120 * steps),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas, event)


def move_to(canvas, point: QPoint, buttons=Qt.MouseButton.NoButton, modifier=None) -> None:
    """A mouse move event straight to the view (``QTest.mouseMove`` goes through the window)."""
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(point),
        canvas.mapToGlobal(QPointF(point)),
        Qt.MouseButton.NoButton,
        buttons,
        modifier or Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move)


def drag(qtbot, canvas, start: QPoint, end: QPoint, modifier=Qt.KeyboardModifier.NoModifier):
    qtbot.mousePress(canvas, LEFT, modifier, start)
    middle = QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2)
    for point in (middle, end):
        move_to(canvas, point, LEFT, modifier)
    qtbot.mouseRelease(canvas, LEFT, modifier, end)


def zoom_pan_turn(qtbot, canvas) -> None:
    """Zoom with the wheel, move with Shift + drag and turn with a drag: a view the user made."""
    wheel(canvas, 3)
    center = QPoint(canvas.width() // 2, canvas.height() // 2)
    drag(qtbot, canvas, center, center + QPoint(40, 25), Qt.KeyboardModifier.ShiftModifier)
    drag(qtbot, canvas, center, center + QPoint(60, -20))
