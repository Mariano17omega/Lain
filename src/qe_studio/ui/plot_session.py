"""A plotted calculation: detection result, loaded data and the user's parameters."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
from matplotlib.figure import Figure

from ..core.calculations import CalculationModule, DetectionResult
from ..core.calculations.params import RenderInfo
from ..core.plotting.style import PlotStyle


@dataclass
class PlotSession:
    result: DetectionResult
    dataset: Any
    params: Any
    defaults: Any = field(init=False)
    info: RenderInfo | None = None

    def __post_init__(self) -> None:
        self.defaults = copy.deepcopy(self.params)

    @property
    def module(self) -> CalculationModule:
        return self.result.module

    @property
    def folder(self) -> Path:
        return self.result.folder

    @property
    def kind(self) -> str:
        return self.result.kind

    @property
    def key(self) -> str:
        return plot_key(self.folder, self.kind)

    @property
    def title(self) -> str:
        return f"{self.module.display_name} · {self.folder.name}"

    def render(self, figure: Figure, style: PlotStyle) -> RenderInfo:
        with matplotlib.rc_context(style.rc(self.params.font_size)):
            self.info = self.module.render(figure, self.dataset, self.params, style)
        return self.info

    def reset_view(self) -> None:
        """Axis limits back to their initial values (keeps colors and other edits)."""
        for name in ("emin", "emax", "xmin", "xmax", "dos_max"):
            if hasattr(self.defaults, name):
                setattr(self.params, name, getattr(self.defaults, name))

    def apply_limits(self, xlim: tuple[float, float], ylim: tuple[float, float]) -> None:
        """Store toolbar pan/zoom limits in the parameters so edits and exports keep them."""
        params = self.params
        if self.kind == "bands":
            params.emin, params.emax = ylim
            params.xmin, params.xmax = xlim
        elif self.kind == "pdos":
            energy, dos = (ylim, xlim) if params.orientation == "vertical" else (xlim, ylim)
            params.emin, params.emax = energy
            params.dos_max = max(abs(dos[0]), abs(dos[1]))


def plot_key(folder: Path, kind: str) -> str:
    return f"plot:{kind}:{folder}"
