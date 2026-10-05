"""Scientific plot tab: themed navigation toolbar + canvas kept at the export aspect ratio."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path

import matplotlib
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...core.calculations.base import AxesLimits
from ...core.plotting.mpl_lock import MPL_LOCK
from ...core.plotting.offscreen import Drawn, Target, draw_offscreen, snapshot
from ...core.plotting.session import PlotSession
from ...core.plotting.style import register_fonts
from ...core.tasks import TaskHandle, run_task
from ..theme.manager import ThemeManager
from .common import IconButton

log = logging.getLogger(__name__)

MARGIN = 16
RETRY_MS = 50  # matplotlib busy with an export: render or draw again after this
RESIZE_MS = 150  # a figure drawn by a worker is drawn again this long after the last resize


class ScaledFigureCanvas(FigureCanvasQTAgg):
    """Keeps the figure size in inches (= export size) and scales dpi with the widget.

    The preview therefore has exactly the layout, font proportions and line weights of the
    exported file, just magnified or reduced.

    A figure that ``worker_draws`` (spec 27-8) is drawn by a worker: the canvas never draws it on a
    resize (``resized`` says the size changed) and takes the worker's picture over with ``adopt``.
    """

    resized = pyqtSignal()

    def __init__(self, figure: Figure):
        super().__init__(figure)
        self._inches = tuple(figure.get_size_inches())
        self.rc: dict = {}  # style rcParams; mathtext is parsed at draw time
        self.worker_draws = False
        # The picture kept (with the bytes it reads) while a resize is redrawn by the worker.
        self._stale: tuple[QImage, bytes] | None = None
        self._redraw = QTimer(self)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(RETRY_MS)
        self._redraw.timeout.connect(self.draw_idle)

    def draw(self) -> None:
        # An export holds matplotlib: keep the last image and draw again shortly, never wait.
        if not MPL_LOCK.acquire(blocking=False):
            redraw = getattr(self, "_redraw", None)  # None while the base class initializes
            if redraw is not None:
                redraw.start()
            return
        try:
            with matplotlib.rc_context(self.rc):
                super().draw()
            self._stale = None  # the figure has its own pixels again
        finally:
            MPL_LOCK.release()

    def set_inches(self, width: float, height: float) -> None:
        self._inches = (width, height)
        self.figure.set_size_inches(width, height, forward=False)

    def adopt(self, drawn: Drawn) -> None:
        """Show the figure a worker drew, with its pixels: it becomes this canvas's figure. Nothing is
        drawn here, so it costs a few attribute writes; pan/zoom draw it again as usual."""
        figure = drawn.figure
        # matplotlib keeps the canvas's event handlers (the toolbar's pan/zoom, ours) on the figure:
        # the new one gets the registry. Its own ``pick`` handlers stay in the old figure's, unused.
        figure._canvas_callbacks = self.figure._canvas_callbacks  # pyright: ignore[reportAttributeAccessIssue]
        figure.set_canvas(self)
        self.figure = figure
        figure._original_dpi = figure.dpi / self.device_pixel_ratio  # pyright: ignore[reportAttributeAccessIssue]
        self._inches = tuple(figure.get_size_inches())
        self.rc = drawn.rc
        # What FigureCanvasAgg.draw leaves behind and ``paintEvent`` reads (``get_renderer``'s key).
        self.renderer = drawn.canvas.renderer
        self._lastKey = drawn.canvas._lastKey  # pyright: ignore[reportAttributeAccessIssue]
        self._draw_pending = False
        self._stale = None
        self.update()

    def _keep_picture(self) -> None:
        """Before a resize: keep what is on show, to stretch it until the worker's new picture
        arrives (the resized figure has no pixels yet)."""
        renderer = getattr(self, "renderer", None)
        if self._stale is None and renderer is not None:
            data = bytes(renderer.buffer_rgba())
            image = QImage(data, renderer.width, renderer.height, QImage.Format.Format_RGBA8888)
            self._stale = (image, data)  # the image does not own its bytes

    def paintEvent(self, event) -> None:
        if self._stale is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(self.rect(), self._stale[0])
        finally:
            painter.end()

    def resizeEvent(self, event) -> None:
        if self.worker_draws:
            self._keep_picture()
        width_in = self._inches[0]
        logical_dpi = max(event.size().width() / width_in, 10.0)
        # Private matplotlib API, the same calls its own Qt canvas makes when the screen changes.
        self.figure._original_dpi = logical_dpi  # pyright: ignore[reportAttributeAccessIssue]
        self.figure._set_dpi(  # pyright: ignore[reportAttributeAccessIssue]
            logical_dpi * self.device_pixel_ratio, forward=False
        )
        super().resizeEvent(event)
        if self.worker_draws:
            self._draw_pending = False  # the base class queued a draw: the worker draws instead
            self.resized.emit()


class AspectBox(QWidget):
    """Centers ``child`` with a fixed width/height ratio inside the available area."""

    def __init__(self, child: QWidget, ratio: float, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plotCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.child, self.ratio = child, ratio
        self.frame = QWidget(self)
        self.frame.setObjectName("plotFrame")
        self.frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        child.setParent(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(QSize(200, 150))

    def set_ratio(self, ratio: float) -> None:
        self.ratio = ratio
        self._layout_child()

    def target_rect(self) -> QRect:
        area = self.rect().adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        width = min(area.width(), int(area.height() * self.ratio))
        height = int(width / self.ratio)
        return QRect(
            area.left() + (area.width() - width) // 2,
            area.top() + (area.height() - height) // 2,
            width,
            height,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_child()

    def _layout_child(self) -> None:
        rect = self.target_rect()
        self.child.setGeometry(rect)
        self.frame.setGeometry(rect.adjusted(-1, -1, 1, 1))
        self.frame.lower()


def _readout(session: PlotSession, axes_index: int, x: float, y: float) -> str:
    return session.format_coordinates(x, y, axes_index)


class _Navigation(NavigationToolbar2QT):
    """Hidden matplotlib toolbar used as pan/zoom controller; messages go to our label."""

    on_message: Callable[[str], None] | None = None

    def set_message(self, s: str) -> None:
        if self.on_message is not None:
            self.on_message(s)


class PlotToolbar(QWidget):
    export_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    navigated = pyqtSignal()  # Back/Forward changed the axis limits

    def __init__(
        self, theme: ThemeManager, canvas: FigureCanvasQTAgg, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setObjectName("plotToolbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.nav = _Navigation(canvas, self, coordinates=False)
        self.nav.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        def tool(icon: str, text: str, tip: str, checkable: bool = False) -> IconButton:
            button = IconButton(theme, icon, tip, "plotTool", "text_secondary", "accent", 15)
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setCheckable(checkable)
            layout.addWidget(button)
            return button

        self.reset = tool("home", "Reset", "Restaurar limites iniciais")
        self.back = tool("arrow_back", "", "Vista anterior")
        self.forward = tool("arrow_forward", "", "Próxima vista")
        self.pan = tool("pan_tool", "", "Mover (arrastar)", checkable=True)
        self.zoom = tool("zoom_in", "", "Zoom (retângulo)", checkable=True)
        self.message = QLabel()
        self.message.setObjectName("plotMessage")
        layout.addWidget(self.message, 1)
        self.export = tool("download", "Exportar", "Salvar em plots/ (Ctrl+E)")

        self.reset.clicked.connect(self.reset_requested)
        self.back.clicked.connect(self._back)
        self.forward.clicked.connect(self._forward)
        self.pan.clicked.connect(self._pan)
        self.zoom.clicked.connect(self._zoom)
        self.export.clicked.connect(self.export_requested)
        self.nav.on_message = self.message.setText

    def _back(self) -> None:
        self.nav.back()
        self.navigated.emit()

    def _forward(self) -> None:
        self.nav.forward()
        self.navigated.emit()

    def _pan(self) -> None:
        self.nav.pan()
        self._sync_modes()

    def _zoom(self) -> None:
        self.nav.zoom()
        self._sync_modes()

    def _sync_modes(self) -> None:
        mode = getattr(self.nav.mode, "name", "")
        self.pan.setChecked(mode == "PAN")
        self.zoom.setChecked(mode == "ZOOM")


class PlotView(QWidget):
    """One plot tab. The session holds data and parameters; the view only draws."""

    limits_changed = pyqtSignal()
    export_requested = pyqtSignal()
    rendered = pyqtSignal(object)  # RenderInfo
    drawing_changed = pyqtSignal(
        str, bool
    )  # session key, a worker is drawing the figure (spec 27-8)

    def __init__(self, theme: ThemeManager, session: PlotSession, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plotView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme, self.session = theme, session
        # Axis limits the params already describe, per session the axes belong to (a grid's cells).
        self._limits: dict[int, AxesLimits] = {}
        self._retry = QTimer(self)  # render again once an export releases matplotlib
        self._retry.setSingleShot(True)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self.render)
        # A figure drawn by a worker (``render_in_worker``): its task, the picture it was asked for
        # (or the one on show) and the pause after a resize.
        self._task: TaskHandle | None = None
        self._target_now: Target | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(RESIZE_MS)
        self._resize_timer.timeout.connect(self._redraw_after_resize)
        register_fonts()
        params = session.params
        self.figure = Figure(figsize=params.figure_size)
        self.canvas = ScaledFigureCanvas(self.figure)
        self.canvas.worker_draws = session.module.render_in_worker
        self.canvas.resized.connect(self._on_resized)
        self.toolbar = PlotToolbar(theme, self.canvas)
        self.box = AspectBox(self.canvas, params.figure_width / params.figure_height)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.box, 1)
        self.toolbar.export_requested.connect(self.export_requested)
        self.toolbar.reset_requested.connect(self._reset)
        self.toolbar.navigated.connect(self._on_release)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("scroll_event", self._on_release)
        self.render()

    @property
    def path(self) -> Path:
        """What the plot shows: its folder, or the output file of a single-file module."""
        return self.session.plot_target

    @property
    def paths(self) -> tuple[Path, ...]:
        """Every folder the plot shows (two for bands + DOS): renaming any closes the tab."""
        return self.session.paths

    @property
    def render_pending(self) -> bool:
        """A render waits for an export to release matplotlib, or a worker is drawing the figure."""
        return self._retry.isActive() or self.drawing or self._resize_timer.isActive()

    @property
    def drawing(self) -> bool:
        """A worker is drawing the figure (``render_in_worker``); the last picture stays meanwhile."""
        return self._task is not None

    def render(self) -> None:
        """Draw the session. While an export holds matplotlib (``MPL_LOCK``) the render is
        retried a moment later instead: the GUI thread never waits for the export. A figure that
        takes seconds (``render_in_worker``) is drawn by a worker and shown when it is done."""
        if self.session.module.render_in_worker:
            self._render_in_worker()
            return
        if not MPL_LOCK.acquire(blocking=False):
            self._retry.start()
            return
        try:
            params = self.session.params
            self._apply_figure_size(params)
            style = self.session.style  # not the app theme: the figure looks like the export
            self.canvas.rc = style.rc(params.font_size)
            info = self.session.render(self.figure, style)
            self._install_readout()
            self._limits = self._axis_limits()
            self.canvas.draw_idle()
            self.toolbar.nav.update()  # drop the pan/zoom history of the previous drawing
        finally:
            MPL_LOCK.release()
        self.rendered.emit(info)

    def _apply_figure_size(self, params) -> None:
        if self.canvas._inches != params.figure_size:
            self.canvas.set_inches(*params.figure_size)
            self.box.set_ratio(params.figure_width / params.figure_height)

    # -- a figure drawn by a worker (spec 27-8 R2 step 3) --------------------------------------------
    def _target(self, params) -> Target:
        """The picture the canvas shows now: what its resize event would make of the dpi."""
        logical_dpi = max(self.canvas.width() / params.figure_width, 10.0)
        return Target(params.figure_size, logical_dpi * self.canvas.device_pixel_ratio)

    def _render_in_worker(self) -> None:
        """Draw the session's parameters as they are now in a worker; a render still running is
        superseded (it stops between cells). The picture on show stays until the new one is ready."""
        self._resize_timer.stop()
        self._retry.stop()
        if self._task is not None:
            self._task.cancel()
        params = snapshot(self.session)
        self._apply_figure_size(
            params
        )  # a resize of the canvas may follow: ``_on_resized`` sees it
        self._target_now = self._target(params)
        self._task = run_task(
            draw_offscreen,
            self.session,
            params,
            self._target_now,
            on_done=self._adopt,
            on_error=self._draw_failed,
        )
        self.drawing_changed.emit(self.session.key, True)

    def _adopt(self, drawn: Drawn) -> None:
        """The worker is done: the figure and its pixels replace what is on show."""
        self._task = None
        if drawn.target != self._target(self.session.params):
            self._render_in_worker()  # the size changed while drawing: this picture does not fit
            return
        self.figure = drawn.figure
        self.canvas.adopt(drawn)
        self._install_readout()
        self._limits = self._axis_limits()
        self.toolbar.nav.update()  # drop the pan/zoom history of the previous drawing
        self.drawing_changed.emit(self.session.key, False)
        self.rendered.emit(drawn.info)

    def _draw_failed(self, error: Exception) -> None:
        self._task = None
        self.drawing_changed.emit(self.session.key, False)
        log.error("drawing %s failed", self.session.kind, exc_info=error)
        raise error  # the window's exception reporter shows it, like a render on the GUI thread

    def _on_resized(self) -> None:
        if self._target_now is not None and self._target_now != self._target(self.session.params):
            self._resize_timer.start()  # the resize may go on: draw once it stops

    def _redraw_after_resize(self) -> None:
        if self._target_now != self._target(self.session.params):
            self._render_in_worker()

    def cancel_load(self) -> None:
        """Window close or tab close: the figure being drawn is not needed any more."""
        self._resize_timer.stop()
        if self._task is not None:
            self._task.cancel()
            self._task = None
            self.drawing_changed.emit(self.session.key, False)

    def _install_readout(self) -> None:
        """The module words the cursor readout of every axes (the toolbar shows it in
        ``#plotMessage``). Rendering rebuilds the axes, so this runs after every render.

        Each axes reads out through the session it belongs to, with its index there: the plot's
        own, or a grid cell's (``PlotSession.routes``). The closures hold the session, never the
        view: the figure belongs to the view, and a reference back to it would keep a closed tab
        alive.
        """
        for ax, (owner, index) in zip(
            self.figure.axes, self.session.routes(self.figure), strict=True
        ):
            ax.format_coord = partial(_readout, owner, index)  # type: ignore[method-assign]

    def _owners(self) -> list[PlotSession]:
        """The sessions the axes belong to: this plot's, or each cell's of a grid."""
        owners = {id(owner): owner for owner, _index in self.session.routes(self.figure)}
        return list(owners.values()) or [self.session]

    def _reset(self) -> None:
        for owner in self._owners():
            owner.reset_view()
        self.render()
        self.limits_changed.emit()

    def _axis_limits(self) -> dict[int, AxesLimits]:
        """``(xlim, ylim)`` of every axes in ``figure.axes`` order, grouped by the session they
        belong to (keyed by its ``id``): what each one's ``apply_limits`` gets."""
        limits: dict[int, AxesLimits] = {}
        for ax, (owner, _index) in zip(
            self.figure.axes, self.session.routes(self.figure), strict=True
        ):
            limits.setdefault(id(owner), []).append((ax.get_xlim(), ax.get_ylim()))
        return limits

    def _on_release(self, _event=None) -> None:
        """Pan/zoom, scroll or Back/Forward: store the new view in the params (exports). In a grid
        only the cells whose view changed are told, so the others keep their automatic limits."""
        limits = self._axis_limits()
        owners = {id(owner): owner for owner in self._owners()}
        # Compared with the last stored view, not the rendered one: Back to the first view
        # must still undo a zoom already written into the params.
        changed = [key for key, view in limits.items() if view != self._limits.get(key)]
        if not changed:
            return
        self._limits = limits
        for key in changed:
            owners[key].apply_limits(limits[key])
        self.limits_changed.emit()
