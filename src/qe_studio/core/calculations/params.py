"""Plot parameters shared by plottable modules and the schema the tuning panel is built from."""

from __future__ import annotations

from dataclasses import KW_ONLY, dataclass, field
from typing import Literal

FieldKind = Literal["float", "int", "bool", "color", "choice", "text", "labels", "series"]

SECTIONS = ("Energia", "Eixo X", "Estilo", "Projeções", "Legenda", "Figura", "Exportar")


@dataclass(frozen=True)
class ParamField:
    name: str
    label: str
    section: str
    kind: FieldKind
    _: KW_ONLY
    choices: tuple[tuple[object, str], ...] = ()  # (value, label)
    minimum: float | None = None
    maximum: float | None = None
    step: float = 0.1
    decimals: int = 2
    suffix: str = ""
    optional: bool = False  # float that may be None (= automatic)
    tooltip: str = ""


@dataclass
class CommonParams:
    title: str = ""
    figure_width: float = 6.0
    figure_height: float = 4.5
    font_size: float = 11.0
    background: str = "#ffffff"  # figure and axes; text follows it (figure_style)
    line_width: float = 1.2
    show_legend: bool = False
    legend_loc: str = "best"
    legend_frame: bool = False
    export_png: bool = True
    export_svg: bool = True
    export_pdf: bool = True
    export_dpi: int = 300

    @property
    def figure_size(self) -> tuple[float, float]:
        return (self.figure_width, self.figure_height)

    @property
    def export_formats(self) -> list[str]:
        return [
            fmt
            for fmt, enabled in (
                ("png", self.export_png),
                ("svg", self.export_svg),
                ("pdf", self.export_pdf),
            )
            if enabled
        ]


def apply_common_config(params: CommonParams, config) -> None:
    """Fill the shared defaults from ``AppConfig`` (``plot`` section)."""
    plot = config.plot
    params.figure_width, params.figure_height = plot.figure_size
    params.line_width = plot.line_width
    params.background = plot.background
    params.export_png = "png" in plot.export.formats
    params.export_svg = "svg" in plot.export.formats
    params.export_pdf = "pdf" in plot.export.formats
    params.export_dpi = plot.export.dpi


LEGEND_LOCATIONS = (
    ("best", "Automática"),
    ("upper right", "Superior direita"),
    ("upper left", "Superior esquerda"),
    ("lower right", "Inferior direita"),
    ("lower left", "Inferior esquerda"),
    ("center right", "Centro direita"),
    ("outside", "Fora (direita)"),
)

COMMON_FIELDS = (
    ParamField("line_width", "Espessura", "Estilo", "float", minimum=0.1, maximum=6, step=0.1),
    ParamField("show_legend", "Mostrar legenda", "Legenda", "bool"),
    ParamField("legend_loc", "Posição", "Legenda", "choice", choices=LEGEND_LOCATIONS),
    ParamField("legend_frame", "Moldura", "Legenda", "bool"),
    ParamField("title", "Título", "Figura", "text"),
    ParamField(
        "figure_width", "Largura", "Figura", "float", minimum=1, maximum=30, step=0.5, suffix="in"
    ),
    ParamField(
        "figure_height", "Altura", "Figura", "float", minimum=1, maximum=30, step=0.5, suffix="in"
    ),
    ParamField("font_size", "Fonte", "Figura", "float", minimum=5, maximum=30, step=1, suffix="pt"),
    ParamField("background", "Cor de fundo", "Figura", "color"),
    ParamField("export_png", "PNG", "Exportar", "bool"),
    ParamField("export_svg", "SVG", "Exportar", "bool"),
    ParamField("export_pdf", "PDF", "Exportar", "bool"),
    ParamField(
        "export_dpi",
        "Resolução PNG",
        "Exportar",
        "choice",
        choices=((300, "300 DPI"), (600, "600 DPI")),
    ),
)


@dataclass(frozen=True)
class RenderInfo:
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    summary: str = ""  # one-line readout for the status bar (E_F, gap, …)
    notes: tuple[str, ...] = field(default_factory=tuple)
