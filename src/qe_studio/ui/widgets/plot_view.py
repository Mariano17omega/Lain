"""Scientific plot tab: themed navigation toolbar + canvas kept at the export aspect ratio."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import matplotlib
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...core.calculations.base import AxesLimits
from ...core.plotting.mpl_lock import MPL_LOCK
from ...core.plotting.session import PlotSession
from ...core.plotting.style import register_fonts
from ..theme.manager import ThemeManager
from .common import IconButton

MARGIN = 16
RETRY_MS = 50  # matplotlib busy with an export: render or draw again after this


class ScaledFigureCanvas(FigureCanvasQTAgg):
    """Keeps the figure size in inches (= export size) and scales dpi with the widget.

    The preview therefore has exactly the layout, font proportions and line weights of the
    exported file, just magnified or reduced.
    """

    def __init__(self, figure: Figure):
        super().__init__(figure)
        self._inches = tuple(figure.get_size_inches())
        self.rc: dict = {}  # style rcParams; mathtext is parsed at draw time
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
        finally:
            MPL_LOCK.release()

    def set_inches(self, width: float, height: float) -> None:
        self._inches = (width, height)
        self.figure.set_size_inches(width, height, forward=False)

    def resizeEvent(self, event) -> None:
        width_in = self._inches[0]
        logical_dpi = max(event.size().width() / width_in, 10.0)
        # Private matplotlib API, the same calls its own Qt canvas makes when the screen changes.
        self.figure._original_dpi = logical_dpi  # pyright: ignore[reportAttributeAccessIssue]
        self.figure._set_dpi(  # pyright: ignore[reportAttributeAccessIssue]
            logical_dpi * self.device_pixel_ratio, forward=False
        )
        super().resizeEvent(event)


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

    def __init__(self, theme: ThemeManager, session: PlotSession, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plotView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme, self.session = theme, session
        self._limits: AxesLimits | None = None  # axis limits the params already describe
        self._retry = QTimer(self)  # render again once an export releases matplotlib
        self._retry.setSingleShot(True)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self.render)
        register_fonts()
        params = session.params
        self.figure = Figure(figsize=params.figure_size)
        self.canvas = ScaledFigureCanvas(self.figure)
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
        """A render waits for an export to release matplotlib."""
        return self._retry.isActive()

    def render(self) -> None:
        """Draw the session. While an export holds matplotlib (``MPL_LOCK``) the render is
        retried a moment later instead: the GUI thread never waits for the export."""
        if not MPL_LOCK.acquire(blocking=False):
            self._retry.start()
            return
        try:
            params = self.session.params
            if self.canvas._inches != params.figure_size:
                self.canvas.set_inches(*params.figure_size)
                self.box.set_ratio(params.figure_width / params.figure_height)
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

    def _install_readout(self) -> None:
        """The module words the cursor readout of every axes (the toolbar shows it in
        ``#plotMessage``). Rendering rebuilds the axes, so this runs after every render.

        The closures hold the session, never the view: the figure belongs to the view, and a
        reference back to it would keep a closed tab alive.
        """
        for index, ax in enumerate(self.figure.axes):
            ax.format_coord = partial(_readout, self.session, index)  # type: ignore[method-assign]

    def _reset(self) -> None:
        self.session.reset_view()
        self.render()
        self.limits_changed.emit()

    def _axis_limits(self) -> AxesLimits | None:
        """``(xlim, ylim)`` of every axes, in ``figure.axes`` order (what ``apply_limits`` gets)."""
        if not self.figure.axes:
            return None
        return [(ax.get_xlim(), ax.get_ylim()) for ax in self.figure.axes]

    def _on_release(self, _event=None) -> None:
        """Pan/zoom, scroll or Back/Forward: store the new view in the params (exports)."""
        limits = self._axis_limits()
        # Compared with the last stored view, not the rendered one: Back to the first view
        # must still undo a zoom already written into the params.
        if limits is None or limits == self._limits:
            return
        self._limits = limits
        self.session.apply_limits(limits)
        self.limits_changed.emit()
