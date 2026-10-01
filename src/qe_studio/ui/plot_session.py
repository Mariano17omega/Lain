"""A plotted calculation: detection result, loaded data and the user's parameters."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic

import matplotlib
from matplotlib.figure import Figure

from ..core.calculations import DetectionResult
from ..core.calculations.base import AxesLimits, CalculationModule, D, P
from ..core.calculations.params import RenderInfo
from ..core.plotting.style import PlotStyle, figure_style

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

    def render(self, figure: Figure, style: PlotStyle) -> RenderInfo:
        with matplotlib.rc_context(style.rc(self.params.font_size)):
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
