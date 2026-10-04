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
from matplotlib.figure import Figure

from ..calculations import DetectionResult
from ..calculations.base import AxesLimits, CalculationModule, D, P, SniffFn
from ..calculations.params import RenderInfo
from ..detection import ManualTarget
from .mpl_lock import MPL_LOCK
from .plot_file import apply_stored, stored_params
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
    def key(self) -> str:
        return plot_key(self.plot_target, self.kind)

    @property
    def style(self) -> PlotStyle:
        """Figure colors from the background parameter, the same for preview and export."""
        return figure_style(self.params.background)

    @property
    def title(self) -> str:
        return f"{self.module.display_name} · {self.plot_target.name}"

    @property
    def edited(self) -> bool:
        return self.params != self.defaults

    def render(self, figure: Figure, style: PlotStyle) -> RenderInfo:
        with MPL_LOCK, matplotlib.rc_context(style.rc(self.params.font_size)):
            self.info = self.module.render(figure, self.dataset, self.params, style)
        return self.info

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


def plot_key(target: Path, kind: str) -> str:
    return f"plot:{kind}:{target}"


def target_key(target: DetectionResult | ManualTarget) -> str:
    """Key of the plot ``target`` shows (the workspace tab, the ``.plot`` writes)."""
    return plot_key(target.plot_target, target.kind)


def load_plot(
    target: DetectionResult | ManualTarget, sniff: SniffFn
) -> tuple[DetectionResult, Any]:
    """Worker: the detection result (a manual mapping is matched here) and its data. ``sniff`` is
    the detection service's cache: the files were sniffed already. Raises ``LoadError`` (message
    for the user) or any parsing error."""
    result = target.build() if isinstance(target, ManualTarget) else target
    return result, result.module.load_cached(result, sniff)


def build_session(
    result: DetectionResult,
    dataset: Any,
    config: AppConfig,
    stored: tuple[dict[str, Any] | None, list[str]],
    memory: FolderMemory,
    open_session: PlotSession | None = None,
) -> tuple[PlotSession, list[str]]:
    """The session of a loaded plot, and the warnings for the user.

    Parameters: the module defaults (kept as the session's ``defaults``), then the stored
    ``<kind>.plot`` (``stored`` is ``read_plot_file``'s answer) or, without one, the settings kept
    in ``FolderMemory`` before ``.plot`` existed. Regenerating an edited open plot
    (``open_session``) keeps its edits instead: they may not have reached the file yet.
    """
    module = result.module
    params = module.default_params(config, dataset)
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
