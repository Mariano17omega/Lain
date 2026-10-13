"""The 3D drawing widget: owns the scene, the camera, the selection and the mouse gestures."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QWidget

from viewer3d.core.bonds import BondGraph, Bonds, bonds_for
from viewer3d.core.camera import Camera
from viewer3d.core.replicate import Scene, build_scene
from viewer3d.core.structure import AtomRef, Structure
from viewer3d.ui.options import DisplayOptions
from viewer3d.ui.renderer_paint import FrameStats, PaintRenderer

MAX_SELECTION = 4  # a dihedral needs four atoms
DRAFT_PRIMITIVES = 1500  # above this many primitives, interaction uses the draft mode
DRAFT_RESTORE_MS = 150
CLICK_SLOP_PX = 4.0
WHEEL_STEP = 1.2  # zoom factor per wheel notch
KEY_ZOOM = 1.15


class Canvas(QWidget):
    selection_changed = pyqtSignal(list)  # list[AtomRef], in click order
    current_changed = pyqtSignal(object)  # AtomRef | None, last clicked atom
    hovered = pyqtSignal(object)  # AtomRef | None
    frame_rendered = pyqtSignal(float)  # ms of the last frame
    options_changed = pyqtSignal()  # options modified from inside the canvas (key P, ...)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.options = DisplayOptions()
        self.camera = Camera()
        self.renderer = PaintRenderer()
        self.structure: Structure | None = None
        self.bonds: Bonds | None = None
        self.graph: BondGraph | None = None
        self.scene: Scene | None = None
        self.selection: list[AtomRef] = []
        self.current: AtomRef | None = None
        self.hover: AtomRef | None = None
        self.draft = False
        self._built_factor: float | None = None
        self._built_reps: tuple[int, int, int] | None = None
        self._press: QPointF | None = None
        self._mode = ""  # "rotate" | "pan" while a button is held
        self._moved = False
        self._last = QPointF()
        # the only timer: back to full quality shortly after the last interaction event
        self._restore = QTimer(self)
        self._restore.setSingleShot(True)
        self._restore.setInterval(DRAFT_RESTORE_MS)
        self._restore.timeout.connect(self._leave_draft)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(240, 240)

    # --- data ---------------------------------------------------------------------------
    def set_structure(self, structure: Structure | None) -> None:
        self.structure = structure
        self.selection = []
        self.current = None
        self.hover = None
        self._built_factor = self._built_reps = None
        if structure is None:
            self.bonds = self.graph = self.scene = None
            self.update()
            return
        self.renderer.set_structure(structure)
        self.refresh_options()
        self.reset_view()
        self.selection_changed.emit([])
        self.current_changed.emit(None)

    def refresh_options(self) -> None:
        """Rebuild what depends on the options (bonds, replicated scene) and repaint."""
        structure, opts = self.structure, self.options
        if structure is None:
            return
        reframe = False
        if self._built_factor != opts.bond_factor:
            self.bonds = bonds_for(structure, opts.bond_factor)
            self.graph = BondGraph(self.bonds, len(structure))
            self._built_factor = opts.bond_factor
            self._built_reps = None
        if self._built_reps != tuple(opts.reps):
            self.scene = build_scene(structure, self.bonds, tuple(opts.reps))
            self._built_reps = tuple(opts.reps)
            reframe = True
        if reframe:
            self._fit_keep_rotation()  # the block changed size: frame it again
        self.update()

    def reset_view(self) -> None:
        if self.scene is None:
            return
        corners = self.scene.box_corners(self.scene.block)
        self.camera.reset(
            self.scene.bounds_points(),
            self._viewport(),
            corners.mean(axis=0),
            pad=self.renderer.max_world_radius(self.options),
        )
        self.update()

    def view_along(self, name: str) -> None:
        if self.structure is not None:
            self.camera.view_axis(name, self.structure.cell)
            self._fit_keep_rotation()

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

    # --- selection ----------------------------------------------------------------------
    def set_selection(self, refs: list[AtomRef], current: AtomRef | None = None) -> None:
        self.selection = list(refs)[:MAX_SELECTION]
        self.current = current if current is not None else (self.selection[-1:] or [None])[0]
        self.selection_changed.emit(list(self.selection))
        self.current_changed.emit(self.current)
        self.update()

    def select(self, ref: AtomRef | None, toggle: bool = False) -> None:
        """Apply the click rules: add, Ctrl-toggle, or clear on empty space."""
        if ref is None:
            if self.selection or self.current is not None:
                self.set_selection([], None)
            return
        refs = list(self.selection)
        if toggle:
            if ref in refs:
                refs.remove(ref)
                self.set_selection(refs, refs[-1] if refs else None)
            else:
                refs = (refs + [ref])[-MAX_SELECTION:]
                self.set_selection(refs, ref)
        elif ref in refs:
            self.set_selection(refs, ref)
        else:
            refs = [ref] if len(refs) >= MAX_SELECTION else refs + [ref]
            self.set_selection(refs, ref)

    # --- painting -----------------------------------------------------------------------
    def _viewport(self) -> tuple[float, float]:
        return float(self.width()), float(self.height())

    def _paint(self, painter: QPainter, size: tuple[float, float]) -> FrameStats | None:
        if self.scene is None:
            return None
        return self.renderer.render(
            painter,
            size,
            self.scene,
            self.camera,
            self.options,
            self.selection,
            self.hover,
            self.draft,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        try:
            stats = self._paint(painter, self._viewport())
            if stats is None:
                painter.fillRect(self.rect(), self.palette().window())
        finally:
            painter.end()
        if stats is not None:
            self.frame_rendered.emit(stats.ms)

    def render_image(self, size: QSize, draft: bool = False, dpr: float = 1.0) -> QImage:
        """Render one frame to an image without showing the widget (for --screenshot)."""
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

    # --- draft mode ---------------------------------------------------------------------
    def _primitive_estimate(self) -> int:
        if self.scene is None:
            return 0
        return len(self.scene.positions) + 2 * len(self.scene.bond_a)

    def _interacting(self) -> None:
        """Called by every navigation event: draft while it lasts, full quality after."""
        if self._primitive_estimate() > DRAFT_PRIMITIVES:
            self.draft = True
            self._restore.start()
        self.update()

    def _leave_draft(self) -> None:
        self.draft = False
        self.update()

    # --- mouse --------------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
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

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        was_click = self._mode == "rotate" and not self._moved
        if event.button() == Qt.MouseButton.LeftButton and self._mode == "pan" and not self._moved:
            was_click = True  # a Shift+click that did not drag still selects
        mode, self._mode = self._mode, ""
        if mode and was_click and self.scene is not None:
            pos = event.position()
            ref = self.renderer.pick((pos.x(), pos.y()))
            toggle = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.select(ref, toggle=toggle)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return
        pos = event.position()
        self.camera.zoom_at(WHEEL_STEP**steps, (pos.x(), pos.y()), self._viewport())
        self._interacting()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hover(None)

    def _update_hover(self, pos: QPointF) -> None:
        if self.scene is None:
            return
        self._set_hover(self.renderer.pick((pos.x(), pos.y())))

    def _set_hover(self, ref: AtomRef | None) -> None:
        if ref != self.hover:
            self.hover = ref
            self.hovered.emit(ref)
            self.update()

    # --- keyboard -----------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        handled = True
        if key == Qt.Key.Key_R:
            self.reset_view()
        elif key in (Qt.Key.Key_A, Qt.Key.Key_B, Qt.Key.Key_C):
            self.view_along({Qt.Key.Key_A: "a", Qt.Key.Key_B: "b", Qt.Key.Key_C: "c"}[key])
        elif key in (Qt.Key.Key_X, Qt.Key.Key_Y, Qt.Key.Key_Z):
            self.view_along({Qt.Key.Key_X: "x", Qt.Key.Key_Y: "y", Qt.Key.Key_Z: "z"}[key])
        elif key == Qt.Key.Key_P:
            self.options.perspective = not self.options.perspective
            self.options_changed.emit()
            self.update()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_center(KEY_ZOOM)
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self._zoom_center(1 / KEY_ZOOM)
        else:
            handled = False
        if handled:
            event.accept()
        else:
            super().keyPressEvent(event)

    def _zoom_center(self, factor: float) -> None:
        w, h = self._viewport()
        self.camera.zoom_at(factor, (w / 2, h / 2), (w, h))
        self._interacting()
