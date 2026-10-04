"""A grid of plots in one figure (spec 23): a module built from other plots' sessions, never
detected and never loaded from files (``grid_result`` and the window's loader make its data)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from matplotlib.figure import Figure, FigureBase

# The module, not its names: plot_file imports calculations (circular at import time).
from ...plotting import plot_file
from ...plotting.style import PlotStyle
from ..base import CalculationModule, FileRole, Stores
from ..params import ParamField, RenderInfo
from . import params as params_mod
from .data import GridDataset
from .params import GridParams, fit_size
from .render import position_of, render_grid

if TYPE_CHECKING:
    from ...config import AppConfig
    from ...plotting.session import PlotSession


class GridModule(CalculationModule[GridDataset, GridParams]):
    kind: ClassVar[str] = "grid"
    badge: ClassVar[str] = "GRID"
    display_name: ClassVar[str] = "Grid"
    description: ClassVar[str] = "Grade de gráficos já plotados numa só figura"
    plottable: ClassVar[bool] = True
    selectable: ClassVar[bool] = False  # made from plots, not mapped from files
    plot_file: ClassVar[bool] = False  # its settings live with its definition (grids.json)
    grid_cell: ClassVar[bool] = False  # no grid inside a grid
    roles: ClassVar[tuple[FileRole, ...]] = ()

    # -- plotting ------------------------------------------------------------------------------
    def default_params(self, config: AppConfig, dataset: GridDataset) -> GridParams:
        return params_mod.default_params(config, dataset)

    def param_schema(self, dataset: GridDataset) -> list[ParamField]:
        return list(params_mod.SCHEMA)

    def param_changed(self, dataset: GridDataset, params: GridParams, name: str, old: Any) -> None:
        if name in ("cell_width", "cell_height"):
            fit_size(params)

    def plot_title(self, target: Path, dataset: GridDataset) -> str:
        return f"{self.display_name} · {dataset.spec.name}"

    def export_stem(self, params: GridParams) -> str:
        return f"grid_{params.name}"

    def render(
        self, figure: FigureBase, dataset: GridDataset, params: GridParams, style: PlotStyle
    ) -> RenderInfo:
        return render_grid(figure, dataset, params, style)

    # -- view hooks ----------------------------------------------------------------------------
    def axes_routes(
        self, figure: Figure, dataset: GridDataset
    ) -> list[tuple[PlotSession, int]] | None:
        """Each axes belongs to the session of its cell, at its index in that cell."""
        cols = dataset.spec.cols
        routes = []
        for ax in figure.axes:
            cell = ax.get_figure(root=False)
            position = position_of(figure, cell, cols) if cell is not None else None
            data = dataset.at(*position) if position is not None else None
            if cell is None or data is None or data.session is None:
                return None  # not a figure render_grid drew: leave the axes to the grid
            routes.append((data.session, cell.axes.index(ax)))
        return routes

    # -- settings, saved with the grid's definition ---------------------------------------------
    def stored_params(self, dataset: GridDataset, stores: Stores) -> dict[str, Any]:
        """The saved settings of this grid, validated like a ``.plot``; a saved cell size comes with
        the figure size it makes for this grid's rows and columns."""
        if stores.grids is None:
            return {}
        spec = dataset.spec
        values = stores.grids.params(spec.name)
        params = GridParams()
        ignored = set(plot_file.apply_stored(params, values, self.param_schema(dataset)))
        kept = {name for name in values if name not in ignored and hasattr(params, name)}
        out = {name: getattr(params, name) for name in kept - plot_file.derived_fields(params)}
        for name, figure_name, count in (
            ("cell_width", "figure_width", spec.cols),
            ("cell_height", "figure_height", spec.rows),
        ):
            if name in out:
                out[figure_name] = count * out[name]
        return out

    def save_stored(
        self, dataset: GridDataset, params: GridParams, name: str, stores: Stores
    ) -> None:
        if stores.grids is not None:
            values = plot_file.stored_params(params)
            for derived in plot_file.derived_fields(params):
                values.pop(derived, None)
            stores.grids.save_params(dataset.spec.name, values)
