"""The 3D view of one window: its scene, camera, current atom and the mouse and key gestures.

The camera changes only by a gesture (spec 43 R3): drag (turn; middle button or Shift + drag: move), the
wheel and ``+`` / ``-`` (zoom), R and "Resetar vista", the views along a, b, c, x, y, z (the keys; the
bar's menu lists x, y, z only, spec 46 R1), the "Rotação" buttons (a 45° step about x, y or z, which does
not frame again) and a new repetition (the block changes size: framed again, keeping the rotation).
Clicks, a double click (two clicks), the neighbour table and every field of the panel leave it alone: a new
bond factor rebuilds the scene without framing it again. "Restaurar padrões" is the one request that
replaces the options and frames the view again (``restore_defaults``). A saved view (spec 47) comes in
through ``restore_camera``, before the first frame, which then does not frame it again.

``dirty`` says whether the user changed the view since it opened (spec 47 R3.1), so closing an untouched
window writes nothing: every edit of the panel and of a species (``refresh_options``), the P key, the
gestures (``_interacting``), ``view_along``, ``rotate_structure`` and R / "Resetar vista" set it. Clicks,
hover, the current atom, measures, the panel's sections and a resize do not, nor does the automatic framing
of the first frame (``_frame``, not ``reset_view``).
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from ....core.structure3d.bonds import BondGraph, Bonds, bonds_for
from ....core.structure3d.camera import ROTATION_STEP_DEG, Camera
from ....core.structure3d.model import AtomRef, Structure
from ....core.structure3d.options import DisplayOptions
from ....core.structure3d.replicate import Scene, build_scene
from ....core.structure3d.view_state import CameraState
from ...theme.manager import ThemeManager
from .render_types import FrameStats
from .renderer import PaintRenderer

DRAFT_PRIMITIVES = 1500  # above this many primitives, interaction uses the draft mode
DRAFT_RESTORE_MS = 150
CLICK_SLOP_PX = 4.0
WHEEL_STEP = 1.2  # zoom factor per wheel notch
KEY_ZOOM = 1.15
WHERE = "Visualização 3D"
AXIS_KEYS = {  # key code → view
    Qt.Key.Key_A.value: "a",
    Qt.Key.Key_B.value: "b",
    Qt.Key.Key_C.value: "c",
    Qt.Key.Key_X.value: "x",
    Qt.Key.Key_Y.value: "y",
    Qt.Key.Key_Z.value: "z",
}


class StructureCanvas(QWidget):
    current_changed = pyqtSignal(object)  # AtomRef | None: the atom the panel shows
    hovered = pyqtSignal(object)  # AtomRef | None
    atom_clicked = pyqtSignal(object)  # AtomRef | None (empty space), every click (spec 44)
    escape_pressed = pyqtSignal()
    options_changed = pyqtSignal()  # options changed from the view (key P)

    def __init__(
        self,
        theme: ThemeManager,
        structure: Structure,
        options: DisplayOptions | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("structureCanvas")
        self.theme, self.structure = theme, structure
        self.options = options if options is not None else DisplayOptions()
        self.camera = Camera()
        self.renderer = PaintRenderer()
        self.renderer.set_structure(structure)
        self.bonds: Bonds | None = None
        self.graph: BondGraph | None = None
        self.scene: Scene | None = None
        self.current: AtomRef | None = None
        self.hover: AtomRef | None = None
        self.marks: tuple[AtomRef, ...] = ()  # numbered rings: the atoms of a measure (spec 44)
        self.draft = False
        self.restored = False  # "Restaurar padrões" was used (spec 46 R6; spec 47 reads it)
        self.dirty = False  # the user changed options or camera (spec 47: written on close)
        self._framed = False  # the first frame waits for a real size
        self._built_factor: float | None = None
        self._built_reps: tuple[int, int, int] | None = None
        self._press: QPointF | None = None
        self._mode = ""  # "rotate" | "pan" while a button is held
        self._moved = False
        self._last = QPointF()
        # the only timer: back to full quality shortly after the last navigation event
        self._restore = QTimer(self)
        self._restore.setSingleShot(True)
        self._restore.setInterval(DRAFT_RESTORE_MS)
        self._restore.timeout.connect(self._leave_draft)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(240, 240)
        self.setAccessibleName("Vista 3D da estrutura")
        self.refresh_options()
        self.dirty = False  # building is no change

    @staticmethod
    def shortcut_help() -> list[tuple[str, str, str]]:
        """(action, keys, where) of the gestures of the view, for the shortcuts dialog."""
        return [
            ("Girar a vista", "Arrastar", WHERE),
            ("Mover a vista", "Shift+Arrastar ou botão do meio", WHERE),
            ("Zoom", "Roda, + e -", WHERE),
            ("Resetar vista", "R", WHERE),
            ("Vista ao longo de a, b, c", "A, B, C", WHERE),
            ("Vista ao longo de x, y, z", "X, Y, Z", WHERE),
            ("Alternar perspectiva", "P", WHERE),
            ("Selecionar átomo", "Clique", WHERE),
            ("Descartar os átomos de uma medida", "Esc", WHERE),
        ]

    # -- data --------------------------------------------------------------------------------------
    def refresh_options(self) -> None:
        """Rebuild what depends on the options (bonds, replicated scene) and repaint. Only a new
        repetition frames the scene again."""
        structure, opts = self.structure, self.options
        rebuild = self._built_factor != opts.bond_factor
        if rebuild:
            self.bonds = bonds_for(structure, opts.bond_factor)
            self.graph = BondGraph(self.bonds, len(structure))
            self._built_factor = opts.bond_factor
        reps = (int(opts.reps[0]), int(opts.reps[1]), int(opts.reps[2]))
        new_reps = self._built_reps != reps
        if (rebuild or new_reps) and self.bonds is not None:
            self.scene = build_scene(structure, self.bonds, reps)
            self._built_reps = reps
        if new_reps and self._framed:
            self._fit_keep_rotation()  # the block changed size
        self.dirty = True
        self.update()

    @property
    def framed(self) -> bool:
        """Whether the camera holds a view yet (framed by the first frame or restored)."""
        return self._framed

    def reset_view(self) -> None:
        """Isometric view of the whole block (R, "Resetar vista"): a change of the user's."""
        self._frame()
        self.dirty = True

    def restore_camera(self, state: CameraState) -> None:
        """A saved view (spec 47 R2.3): rotation, zoom, pan and focal as they were, centred on the block
        like a framed one; the first frame keeps it, and it is no change of the user's."""
        state.apply(self.camera)
        if self.scene is not None:
            self.camera.center = self.scene.box_corners(self.scene.block).mean(axis=0)
        self._framed = True
        self.dirty = False
        self.update()

    def _frame(self, viewport: tuple[float, float] | None = None) -> None:
        """Isometric view of the whole block, framed in ``viewport`` (the view's size by default)."""
        if self.scene is None:
            return
        corners = self.scene.box_corners(self.scene.block)
        self.camera.reset(
            self.scene.bounds_points(),
            viewport or self._viewport(),
            corners.mean(axis=0),
            pad=self.renderer.max_world_radius(self.options),
        )
        self._framed = True
        self.update()

    def view_along(self, name: str) -> None:
        self.camera.view_axis(name, self.structure.cell)
        self._fit_keep_rotation()
        self.dirty = True

    def rotate_structure(self, axis: str, degrees: float = ROTATION_STEP_DEG) -> None:
        """Turn the structure ``degrees`` about the Cartesian ``axis`` (spec 46 R3). Zoom and position
        stay (the center of the block does not move on the screen); selection and measures are not
        touched."""
        self.camera.rotate_world(axis, degrees)
        self.dirty = True
        self.update()

    def restore_defaults(self, background: str) -> None:
        """Options and camera back to a new window's (spec 46 R6): a new ``DisplayOptions`` with
        ``background``, the species colors and visibility included, and the initial view framed. The
        current atom, the atoms of a measure and the measures belong to the user's work and stay.

        The view is then the defaults, no change to save: ``dirty`` goes back to False and ``restored``
        tells the closing window to remove its saved section (spec 47 R3.5)."""
        self.options = DisplayOptions(background=background)
        self.refresh_options()
        self._frame()
        self.restored = True
        self.options_changed.emit()  # the panel reads every field again
        self.dirty = False

    def _fit_keep_rotation(self) -> None:
        if self.scene is None:
            return
        self.camera.center = self.scene.box_corners(self.scene.block).mean(axis=0)
        self.camera.fit(
            self.scene.bounds_points(),
            self._viewport(),
            pad=self.renderer.max_world_radius(self.options),
        )
        self.update()

    # -- selection ---------------------------------------------------------------------------------
    def select(self, ref: AtomRef | None) -> None:
        """Make ``ref`` the current atom (None clears). The camera does not move."""
        if ref != self.current:
            self.current = ref
            self.current_changed.emit(ref)
        self.update()

    def set_marks(self, refs: tuple[AtomRef, ...] | list[AtomRef]) -> None:
        """Number ``refs`` on the view, in order (the atoms of a measure); the camera does not move."""
        self.marks = tuple(refs)
        self.update()

    # -- painting ----------------------------------------------------------------------------------
    def _viewport(self) -> tuple[float, float]:
        return float(self.width()), float(self.height())

    def _paint(self, painter: QPainter, size: tuple[float, float]) -> FrameStats | None:
        if self.scene is None:
            return None
        if not self._framed:
            self._frame(size)
        return self.renderer.render(
            painter,
            size,
            self.scene,
            self.camera,
            self.options,
            self.current,
            self.hover,
            self.draft,
            self.marks,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if not self._framed and self.width() > 0 and self.height() > 0:
            self._frame()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter, self._viewport())
            if self.hasFocus():
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(self.theme.color("focus_ring"), 1.0))
                painter.drawRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0))
        finally:
            painter.end()

    def render_image(self, size: QSize, draft: bool = False, dpr: float = 1.0) -> QImage:
        """One frame into an image, without showing the widget (tests, measures)."""
        image = QImage(
            QSize(round(size.width() * dpr), round(size.height() * dpr)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(dpr)
        painter = QPainter(image)
        previous, self.draft = self.draft, draft
        try:
            self._paint(painter, (float(size.width()), float(size.height())))
        finally:
            self.draft = previous
            painter.end()
        return image

    @property
    def stats(self) -> FrameStats:
        return self.renderer.stats

    # -- draft mode --------------------------------------------------------------------------------
    def _primitive_estimate(self) -> int:
        if self.scene is None:
            return 0
        return len(self.scene.positions) + 2 * len(self.scene.bond_a)

    def _interacting(self) -> None:
        """Called by every navigation event: draft while it lasts, full quality after."""
        if self._primitive_estimate() > DRAFT_PRIMITIVES:
            self.draft = True
            self._restore.start()
        self.dirty = True
        self.update()

    def _leave_draft(self) -> None:
        self.draft = False
        self.update()

    # -- mouse -------------------------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        self.setFocus()
        pos = event.position()
        self._press = self._last = pos
        self._moved = False
        button = event.button()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if button == Qt.MouseButton.MiddleButton or (button == Qt.MouseButton.LeftButton and shift):
            self._mode = "pan"
        elif button == Qt.MouseButton.LeftButton:
            self._mode = "rotate"
            self.camera.arcball_begin(pos.x(), pos.y(), self._viewport())
        else:
            self._mode = ""

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        """A double click is two clicks: the second press selects like the first (no reset)."""
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        pos = event.position()
        if not self._mode:
            self._update_hover(pos)
            return
        if self._press is not None and not self._moved:
            moved = pos - self._press
            self._moved = abs(moved.x()) + abs(moved.y()) > CLICK_SLOP_PX
        if not self._moved:
            return
        if self._mode == "pan":
            delta = pos - self._last
            self.camera.pan_by(delta.x(), delta.y())
        else:
            self.camera.arcball_drag(pos.x(), pos.y(), self._viewport())
        self._last = pos
        self._interacting()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        left = event.button() == Qt.MouseButton.LeftButton
        was_click = self._mode in ("rotate", "pan") and left and not self._moved
        self._mode = ""
        if was_click and self.scene is not None:
            pos = event.position()
            ref = self.renderer.pick((pos.x(), pos.y()))
            self.select(ref)
            self.atom_clicked.emit(ref)

    def wheelEvent(self, event: QWheelEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return
        pos = event.position()
        self.camera.zoom_at(WHEEL_STEP**steps, (pos.x(), pos.y()), self._viewport())
        self._interacting()
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hover(None)

    def _update_hover(self, pos: QPointF) -> None:
        if self.scene is not None:
            self._set_hover(self.renderer.pick((pos.x(), pos.y())))

    def _set_hover(self, ref: AtomRef | None) -> None:
        if ref != self.hover:
            self.hover = ref
            self.hovered.emit(ref)
            self.update()

    # -- keyboard ----------------------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        key = event.key()
        if key == Qt.Key.Key_R:
            self.reset_view()
        elif key in AXIS_KEYS:
            self.view_along(AXIS_KEYS[key])
        elif key == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
        elif key == Qt.Key.Key_P:
            self.options.perspective = not self.options.perspective
            self.dirty = True
            self.options_changed.emit()
            self.update()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_center(KEY_ZOOM)
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self._zoom_center(1 / KEY_ZOOM)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _zoom_center(self, factor: float) -> None:
        w, h = self._viewport()
        self.camera.zoom_at(factor, (w / 2, h / 2), (w, h))
        self._interacting()
