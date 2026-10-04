"""A plotted calculation: detection result, loaded data and the user's parameters.

``load_plot`` runs in the load worker; ``build_session`` turns its outcome and the stored
``<kind>.plot`` settings into the session a plot tab shows (spec 15 R5).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic

import matplotlib
from matplotlib.figure import Figure, FigureBase

from ..calculations import DetectionResult
from ..calculations.base import AxesLimits, CalculationModule, D, P, SniffFn, Stores
from ..calculations.params import RenderInfo
from ..detection import FolderTarget, ManualTarget, PairTarget
from .grid import PlotRef
from .mpl_lock import MPL_LOCK
from .plot_file import apply_stored, stored_elsewhere, stored_params
from .style import PlotStyle, figure_style

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..folder_memory import FolderMemory

log = logging.getLogger(__name__)


@dataclass
class PlotSession(Generic[D, P]):
    result: DetectionResult
    dataset: D
    params: P
    defaults: P = field(init=False)
    info: RenderInfo | None = None
    _readout_failed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.defaults = copy.deepcopy(self.params)

    @property
    def module(self) -> CalculationModule[D, P]:
        return self.result.module

    @property
    def folder(self) -> Path:
        return self.result.folder

    @property
    def kind(self) -> str:
        return self.result.kind

    @property
    def plot_target(self) -> Path:
        """What the plot shows: the folder, or the one file of a single-output module."""
        return self.result.plot_target

    @property
    def paths(self) -> tuple[Path, ...]:
        """Every folder (or file) the plot shows: two for a figure of two folders (spec 22), all
        of a grid's plots (spec 23)."""
        return self.result.targets

    @property
    def composite(self) -> bool:
        """A figure of several folders' results (bands + DOS, a grid), not the plot of one folder."""
        return bool(self.result.parts or self.result.plot_name)

    @property
    def ref(self) -> PlotRef:
        """What a grid cell keeps to plot this again (spec 23)."""
        paths = self.paths
        return PlotRef(paths[0], self.kind, paths[1] if len(paths) > 1 else None)

    @property
    def key(self) -> str:
        return plot_key(self.result.plot_id, self.kind)

    @property
    def style(self) -> PlotStyle:
        """Figure colors from the background parameter, the same for preview and export."""
        return figure_style(self.params.background)

    @property
    def title(self) -> str:
        return self.module.plot_title(self.plot_target, self.dataset)

    @property
    def edited(self) -> bool:
        return self.params != self.defaults

    def render(self, figure: FigureBase, style: PlotStyle, params: P | None = None) -> RenderInfo:
        """Draw into ``figure`` (a grid cell is a ``SubFigure``); ``params`` instead of the
        session's (a grid cell with its own title draws a copy without the plot's)."""
        params = self.params if params is None else params
        with MPL_LOCK, matplotlib.rc_context(style.rc(params.font_size)):
            self.info = self.module.render(figure, self.dataset, params, style)
        return self.info

    def routes(self, figure: Figure) -> list[tuple[PlotSession, int]]:
        """The session and its own axes index of every axes of ``figure``: this one for a plot, a
        cell's for a grid (readout, pan/zoom and Reset go there)."""
        routes = self.module.axes_routes(figure, self.dataset)
        return routes if routes is not None else [(self, i) for i in range(len(figure.axes))]

    def copy(self) -> PlotSession[D, P]:
        """A session with the data of this one and a copy of its parameters (a grid cell takes an
        open plot as it is now: edits made later in its tab are not the grid's)."""
        twin = PlotSession(self.result, self.dataset, copy.deepcopy(self.params))
        twin.defaults = copy.deepcopy(self.defaults)
        return twin

    def format_coordinates(self, x: float, y: float, axes_index: int) -> str:
        """Cursor readout of the module. It runs inside a mouse event: a failure is logged once
        and the readout stays empty, it never reaches Qt."""
        try:
            return self.module.format_coordinates(x, y, axes_index, self.dataset, self.params)
        except Exception:
            if not self._readout_failed:
                self._readout_failed = True
                log.exception("cursor readout of %s failed", self.kind)
            return ""

    def persist(self, name: str, stores: Stores) -> bool:
        """After an edit of ``name``: if it is kept in a user store (not in ``<kind>.plot``), save it
        there and make it the new default, so it is neither a plot edit (no ``.plot`` write) nor
        undone by "Restaurar padrões". False when ``name`` is an ordinary ``.plot`` parameter.
        A module without a ``.plot`` (``plot_file`` False: a grid) keeps every parameter so."""
        if self.module.plot_file and name not in stored_elsewhere(self.params):
            return False
        self.module.save_stored(self.dataset, self.params, name, stores)
        setattr(self.defaults, name, copy.deepcopy(getattr(self.params, name)))
        return True

    def reset_view(self) -> None:
        """Axis limits back to their initial values (keeps colors and other edits)."""
        for name in self.module.view_fields:
            setattr(self.params, name, getattr(self.defaults, name))

    def apply_limits(self, axes_limits: AxesLimits) -> None:
        """Store toolbar pan/zoom limits in the parameters so edits and exports keep them."""
        floats: AxesLimits = [  # Python floats, not numpy scalars
            ((float(x0), float(x1)), (float(y0), float(y1))) for (x0, x1), (y0, y1) in axes_limits
        ]
        self.module.apply_limits(self.params, floats)


def plot_key(target: Path | str, kind: str) -> str:
    return f"plot:{kind}:{target}"


Target = DetectionResult | ManualTarget | PairTarget | FolderTarget


def target_key(target: Target) -> str:
    """Key of the plot ``target`` shows (the workspace tab, the ``.plot`` writes)."""
    return plot_key(target.plot_id, target.kind)


def load_plot(target: Target, sniff: SniffFn) -> tuple[DetectionResult, Any]:
    """Worker: the detection result (a manual mapping is matched here, a pair of folders detected
    and paired) and its data. ``sniff`` is the detection service's cache: the files were sniffed
    already. Raises ``LoadError`` (message for the user) or any parsing error."""
    built = isinstance(target, ManualTarget | PairTarget | FolderTarget)
    result = target.build() if built else target
    return result, result.module.load_cached(result, sniff)


def build_session(
    result: DetectionResult,
    dataset: Any,
    config: AppConfig,
    stored: tuple[dict[str, Any] | None, list[str]],
    memory: FolderMemory,
    open_session: PlotSession | None = None,
    stores: Stores | None = None,
) -> tuple[PlotSession, list[str]]:
    """The session of a loaded plot, and the warnings for the user.

    Parameters: the module defaults, with what the user ``stores`` keep (e.g. the atoms chosen for
    the compound) over them: that is the session's ``defaults``. Then the stored ``<kind>.plot``
    (``stored`` is ``read_plot_file``'s answer) or, without one, the settings kept in
    ``FolderMemory`` before ``.plot`` existed. Regenerating an edited open plot (``open_session``)
    keeps its edits instead: they may not have reached the file yet. Store-kept parameters are
    always read from the store again, never from the open plot.
    """
    module = result.module
    params = module.default_params(config, dataset)
    if stores is not None:
        for name, value in module.stored_params(dataset, stores).items():
            setattr(params, name, value)
    values, warnings = stored
    if open_session is not None and open_session.edited:
        values, warnings = stored_params(open_session.params), []
    if values is None:
        module.legacy_params(params, result.folder, memory)
    session = PlotSession(result, dataset, params)  # defaults: without the stored settings
    if values is not None:
        ignored = apply_stored(params, values, module.param_schema(dataset))
        if ignored:
            log.warning("%s.plot: ignored %s", result.kind, ", ".join(ignored))
    return session, list(warnings)
