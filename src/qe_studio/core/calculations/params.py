"""Plot parameters shared by plottable modules and the schema the tuning panel is built from."""

from __future__ import annotations

from dataclasses import KW_ONLY, dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..config import AppConfig
    from .base import CalculationModule

# "series": a list of hidden series names plus ``ParamField.colors``, the dict of color overrides.
# "atoms": the atoms to plot (``list[int] | None``), picked in a window and kept per compound.
FieldKind = Literal["float", "int", "bool", "color", "choice", "text", "labels", "series", "atoms"]


@dataclass(frozen=True)
class SectionDef:
    name: str
    export: bool = False  # the section that gets the "Salvar em plots/" button


# Sections every plot has. Modules add their own with ``CalculationModule.sections``.
SECTIONS = (
    SectionDef("Energia"),
    SectionDef("Eixo X"),
    SectionDef("Estilo"),
    SectionDef("Legenda"),
    SectionDef("Figura"),
    SectionDef("Exportar", export=True),
)


def ordered_sections(module: CalculationModule) -> tuple[SectionDef, ...]:
    """Common sections with the module's own inserted: ``(name, before)`` pairs.

    ``before`` names the section the new one goes in front of; ``None`` or an unknown name puts it
    just ahead of the export section, which always stays last.
    """
    sections = list(SECTIONS)
    for name, before in module.sections:
        names = [s.name for s in sections]
        if before in names:
            index = names.index(before)
        else:
            index = next((i for i, s in enumerate(sections) if s.export), len(sections))
        sections.insert(index, SectionDef(name))
    return tuple(sections)


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
    refreshes: bool = False  # after an edit the panel re-reads every value (dependent fields)
    colors: str = ""  # kind "series": name of the parameter holding the color overrides


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
    legend_size: float | None = None  # pt; None = 0.85 × font_size
    legend_transparency: float = 0.2  # 0 opaque … 1 invisible (0.2 = matplotlib's frame alpha 0.8)
    tick_size: float | None = None  # tick labels, pt; None = font_size
    label_size: float | None = None  # axis labels, pt; None = font_size
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


def apply_common_config(params: CommonParams, config: AppConfig) -> None:
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

# Only the band and PDOS modules offer it (it is not in COMMON_FIELDS): a gap needs a spectrum.
LEGEND_GAP_FIELD = ParamField(
    "legend_gap",
    "Gap de energia na legenda",
    "Legenda",
    "bool",
    tooltip="Mostra o gap (CBM − VBM) na legenda. Sem efeito com a legenda oculta ou em sistema metálico.",
)

COMMON_FIELDS = (
    ParamField("line_width", "Espessura", "Estilo", "float", minimum=0.1, maximum=6, step=0.1),
    ParamField("show_legend", "Mostrar legenda", "Legenda", "bool"),
    ParamField("legend_loc", "Posição", "Legenda", "choice", choices=LEGEND_LOCATIONS),
    ParamField("legend_frame", "Moldura", "Legenda", "bool"),
    ParamField(
        "legend_size",
        "Tamanho",
        "Legenda",
        "float",
        minimum=4,
        maximum=40,
        step=1,
        suffix="pt",
        optional=True,
        tooltip="Tamanho do texto da legenda. Automático = 85 % da fonte da figura.",
    ),
    ParamField(
        "legend_transparency",
        "Transparência",
        "Legenda",
        "float",
        minimum=0,
        maximum=1,
        step=0.05,
        tooltip="0 = fundo da legenda opaco, 1 = invisível. Vale com a moldura ligada.",
    ),
    ParamField(
        "tick_size",
        "Marcações",
        "Legenda",
        "float",
        minimum=4,
        maximum=40,
        step=1,
        suffix="pt",
        optional=True,
        tooltip="Tamanho dos números nas marcações dos eixos. Automático = fonte da figura.",
    ),
    ParamField(
        "label_size",
        "Rotulagem dos eixos",
        "Legenda",
        "float",
        minimum=4,
        maximum=40,
        step=1,
        suffix="pt",
        optional=True,
        tooltip="Tamanho dos rótulos dos eixos. Automático = fonte da figura.",
    ),
    ParamField("title", "Título", "Figura", "text"),
    ParamField(
        "figure_width", "Largura", "Figura", "float", minimum=1, maximum=30, step=0.5, suffix="in"
    ),
    ParamField(
        "figure_height", "Altura", "Figura", "float", minimum=1, maximum=30, step=0.5, suffix="in"
    ),
    ParamField("font_size", "Fonte", "Figura", "float", minimum=5, maximum=30, step=1, suffix="pt"),
    ParamField("background", "Cor de fundo", "Figura", "color", refreshes=True),
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
