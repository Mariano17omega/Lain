"""Panel layout of the main window (spec 1 R3, spec 3): which panels show, their widths, and the
window state kept in QSettings (``window/geometry``, ``layout/*``, ``files/*``).

Knows nothing of plots or sync: the workflow asks for a panel through the main window.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QSplitter, QStackedWidget, QWidget

from .widgets.bars import ActivityBar, TopBar
from .widgets.file_grid import FilePanel
from .widgets.fs_model import SORT_DATE, SORT_NAME, SORT_SIZE

PANELS: tuple[str, ...] = ("tree", "grid", "workspace")  # splitter order
DEFAULT_PANEL_WIDTHS = {"tree": 280, "grid": 320, "workspace": 840}
PARAMS_PAGE = 1  # the plot parameters in the left panel (0: the explorer tree)


def fit_widths(
    weights: dict[str, int], minimums: dict[str, int], available: int, keep: str | None = None
) -> dict[str, int]:
    """Split ``available`` px among panels in proportion to ``weights``, none below its minimum.

    ``keep`` (a panel shown again) gets its weight as width, reduced until the others fit.
    """
    rest = dict(weights)
    sizes: dict[str, int] = {}
    if keep is not None:
        room = available - sum(minimums[name] for name in rest if name != keep)
        sizes[keep] = max(min(rest.pop(keep), room), minimums[keep])
        available -= sizes[keep]
    while True:
        total = sum(rest.values()) or 1
        pinned = [name for name, w in rest.items() if available * w / total < minimums[name]]
        if not pinned:
            break
        for name in pinned:
            sizes[name] = minimums[name]
            available -= minimums[name]
            del rest[name]
    names = list(rest)
    total = sum(rest.values()) or 1
    for name in names[:-1]:
        sizes[name] = round(available * rest[name] / total)
    if names:  # the last one takes the rounding remainder, so the sum is exact
        sizes[names[-1]] = available - sum(sizes[name] for name in names[:-1])
    return sizes


class LayoutController(QObject):
    workspace_visibility_changed = pyqtSignal(bool)

    def __init__(
        self,
        window: QMainWindow,
        splitter: QSplitter,
        panels: dict[str, QWidget],
        top_bar: TopBar,
        activity: ActivityBar,
        settings: QSettings,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.window, self.splitter, self.panels = window, splitter, panels
        self.top_bar, self.activity, self.settings = top_bar, activity, settings
        left = panels["tree"]
        assert isinstance(left, QStackedWidget)
        self.left = left
        files = panels["grid"]
        assert isinstance(files, FilePanel)
        self.files = files
        for name in PANELS:
            splitter.addWidget(panels[name])
        # Working width of each panel, kept while it is hidden (spec 1 R3). Sizes set by
        # _apply_panel_layout; while the splitter still shows them, the working widths stand.
        self.panel_widths: dict[str, int] = dict(DEFAULT_PANEL_WIDTHS)
        self._applied_sizes: list[int] | None = None
        splitter.splitterMoved.connect(self._on_splitter_moved)
        top_bar.panel_toggled.connect(self.set_panel_visible)
        activity.explorer_requested.connect(self.show_tree)
        activity.grid_toggled.connect(self._on_grid_toggled)

    # -- panels ---------------------------------------------------------------------------------
    def show_tree(self) -> None:
        self.set_left_mode("tree")

    def set_left_mode(self, mode: str) -> None:
        """``tree`` (explorer) or ``params`` (plot parameters) in the left panel, shown."""
        self.left.setCurrentIndex(PARAMS_PAGE if mode == "params" else 0)
        self.activity.set_left_mode(mode)
        self.set_panel_visible("tree", True)

    def plot_shown(self) -> bool:
        """The workspace and the plot parameters are both on screen."""
        return (
            not self.panels["workspace"].isHidden()
            and not self.left.isHidden()
            and self.left.currentIndex() == PARAMS_PAGE
        )

    def set_panel_visible(self, panel: str, visible: bool) -> None:
        widget = self.panels[panel]
        if widget.isHidden() == visible:
            self._sync_panel_widths()
            widget.setVisible(visible)
            self._apply_panel_layout(panel)
        toggle = self.top_bar.toggles[panel]
        toggle.blockSignals(True)
        toggle.setChecked(visible)
        toggle.blockSignals(False)
        if panel == "grid":
            self.activity.grid.blockSignals(True)
            self.activity.grid.setChecked(visible)
            self.activity.grid.blockSignals(False)
        if panel == "workspace":
            self.workspace_visibility_changed.emit(visible)

    def _on_grid_toggled(self, visible: bool) -> None:
        self.set_panel_visible("grid", visible)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self._sync_panel_widths()

    def _sync_panel_widths(self) -> None:
        """Take sizes the user changed (dragged divider, resized window) as working widths.

        While the splitter still shows the sizes set by ``_apply_panel_layout`` the working
        widths stand, so hiding and showing a panel back restores the layout exactly.
        """
        if not self.splitter.isVisible():
            return  # not laid out yet
        sizes = self.splitter.sizes()
        if self._applied_sizes is None:
            # First look after the window was shown: that layout came from the working widths.
            self._applied_sizes = sizes
            return
        if sizes == self._applied_sizes:
            return
        for name, size in zip(PANELS, sizes, strict=True):
            if size > 0:  # hidden panels report 0
                self.panel_widths[name] = size

    def _apply_panel_layout(self, changed: str) -> None:
        """Resize the panels after ``changed`` was shown or hidden (spec 1 R3).

        A hidden panel's space goes to the visible ones in proportion to their widths; a panel
        shown again gets its working width back and the others shrink in proportion.
        """
        shown = [name for name in PANELS if not self.panels[name].isHidden()]
        # The workspace absorbs window resizes; without it (no stretch factor at all) QSplitter
        # shares them in proportion to the panel sizes.
        self.splitter.setStretchFactor(PANELS.index("workspace"), int("workspace" in shown))
        self.splitter.refresh()  # handle visibility now, not on the next LayoutRequest
        widths = {name: self.panel_widths[name] for name in shown}
        visible = self.splitter.isVisible()
        if visible and shown:
            handles = self.splitter.handleWidth() * (len(shown) - 1)
            available = self.splitter.contentsRect().width() - handles
            minimums = {name: self.panels[name].minimumWidth() for name in shown}
            keep = changed if changed in shown else None
            widths = fit_widths(widths, minimums, available, keep)
        # Before the first show the working widths go in as is; the first layout scales them.
        self.splitter.setSizes([widths.get(name, 0) for name in PANELS])
        self._applied_sizes = self.splitter.sizes() if visible else None

    # -- state ----------------------------------------------------------------------------------
    def restore(self) -> None:
        settings = self.settings
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.window.restoreGeometry(geometry)
        # Keys before spec 3: window/splitter (raw sizes, 0 for hidden panels), window/grid_visible.
        for key in ("layout/panel_widths", "window/splitter"):
            widths = [int(w) for w in settings.value(key, [], type=list)]
            if len(widths) == len(PANELS) and min(widths) > 0:
                self.panel_widths = dict(zip(PANELS, widths, strict=True))
                break
        grid_visible = settings.value("window/grid_visible", True, type=bool)
        settings.remove("window/splitter")
        settings.remove("window/grid_visible")
        self.set_panel_visible("tree", settings.value("layout/tree_visible", True, type=bool))
        self.set_panel_visible(
            "grid", settings.value("layout/grid_visible", grid_visible, type=bool)
        )
        # Tabs are not restored, so the workspace would open empty (spec 1 R1).
        self.set_panel_visible("workspace", False)
        self.files.set_grid_mode(settings.value("files/grid_mode", True, type=bool))
        sort = settings.value("files/sort", SORT_NAME, type=int)
        self.files.set_sort(sort if sort in (SORT_NAME, SORT_SIZE, SORT_DATE) else SORT_NAME)

    def save(self) -> None:
        settings = self.settings
        settings.setValue("window/geometry", self.window.saveGeometry())
        self._sync_panel_widths()
        settings.setValue("layout/panel_widths", [self.panel_widths[n] for n in PANELS])
        settings.setValue("layout/tree_visible", not self.left.isHidden())
        settings.setValue("layout/grid_visible", not self.files.isHidden())
        settings.setValue("files/grid_mode", self.files.grid_mode)
        settings.setValue("files/sort", self.files.sort_column)
