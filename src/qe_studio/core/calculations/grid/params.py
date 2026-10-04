"""The grid figure's own parameters (spec 23): cell size, titles, background and export. Each cell
keeps the parameters of its own plot; the grid never edits them."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from ..params import COMMON_FIELDS, CommonParams, ParamField, apply_common_config

if TYPE_CHECKING:
    from ...config import AppConfig
    from .data import GridDataset

DERIVED = {"derived": True}  # set from the grid's definition, never read back from the store


@dataclass
class GridParams(CommonParams):
    cell_width: float = 6.0
    cell_height: float = 4.5
    show_titles: bool = True
    # ``figure_size`` is cols × cell_width by rows × cell_height: computed, not stored.
    figure_width: float = field(default=6.0, metadata=DERIVED)
    figure_height: float = field(default=4.5, metadata=DERIVED)
    name: str = field(default="", metadata=DERIVED)
    rows: int = field(default=1, metadata=DERIVED)
    cols: int = field(default=1, metadata=DERIVED)


def fit_size(params: GridParams) -> None:
    params.figure_width = params.cols * params.cell_width
    params.figure_height = params.rows * params.cell_height


def default_params(config: AppConfig, dataset: GridDataset) -> GridParams:
    params = GridParams()
    apply_common_config(params, config)
    params.cell_width, params.cell_height = config.plot.figure_size
    spec = dataset.spec
    params.name, params.rows, params.cols = spec.name, spec.rows, spec.cols
    fit_size(params)
    return params


_COMMON = {f.name: f for f in COMMON_FIELDS}
SCHEMA = [
    ParamField(
        "cell_width",
        "Largura da célula",
        "Figura",
        "float",
        minimum=1,
        maximum=20,
        step=0.5,
        suffix="in",
    ),
    ParamField(
        "cell_height",
        "Altura da célula",
        "Figura",
        "float",
        minimum=1,
        maximum=20,
        step=0.5,
        suffix="in",
    ),
    ParamField(
        "show_titles",
        "Títulos das células",
        "Figura",
        "bool",
        tooltip="Mostra o título de cada célula no lugar do título do gráfico",
    ),
    replace(_COMMON["font_size"], label="Fonte dos títulos"),
    _COMMON["background"],
    *(_COMMON[name] for name in ("export_png", "export_svg", "export_pdf", "export_dpi")),
]
