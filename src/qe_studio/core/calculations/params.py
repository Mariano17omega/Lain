"""Plot parameters shared by plottable modules and the schema the tuning panel is built from."""

from __future__ import annotations

from dataclasses import KW_ONLY, dataclass, field
from typing import TYPE_CHECKING, Literal

from ...i18n import N_, _

if TYPE_CHECKING:
    from ..config import AppConfig
    from .base import CalculationModule

# "series": a list of hidden series names plus ``ParamField.colors``, the dict of color overrides.
# "atoms": the atoms to plot (``list[int] | None``), picked in a window and kept per compound.
FieldKind = Literal["float", "int", "bool", "color", "choice", "text", "labels", "series", "atoms"]


@dataclass(frozen=True)
class SectionDef:
    """A group of the tuning panel. ``id`` is what ``ParamField.section``, the settings and the
    code use; ``title`` is the (Portuguese) message the panel shows, translated at use."""

    id: str
    title: str
    export: bool = False  # the export section (formats, DPI): always the last one


# Sections every plot has. Modules add their own with ``CalculationModule.sections``.
SECTIONS = (
    SectionDef("energy", N_("Energia")),
    SectionDef("x_axis", N_("Eixo X")),
    SectionDef("style", N_("Estilo")),
    SectionDef("legend", N_("Legenda")),
    SectionDef("figure", N_("Figura")),
    SectionDef("export", N_("Exportar"), export=True),
)


def ordered_sections(module: CalculationModule) -> tuple[SectionDef, ...]:
    """Common sections with the module's own inserted: ``(section, before)`` pairs.

    ``before`` is the id of the section the new one goes in front of; ``None`` or an unknown id puts
    it just ahead of the export section, which always stays last.
    """
    sections = list(SECTIONS)
    for section, before in module.sections:
        ids = [s.id for s in sections]
        if before in ids:
            index = ids.index(before)
        else:
            index = next((i for i, s in enumerate(sections) if s.export), len(sections))
        sections.insert(index, section)
    return tuple(sections)


@dataclass(frozen=True)
class ParamField:
    name: str
    label: str
    section: str
    kind: FieldKind
    __: KW_ONLY
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
    requires: str = ""  # name of a bool parameter the field does nothing without (panel: disabled)


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
    # Shift of the legend as a fraction of its axes (positive: right / up), spec 36.
    legend_dx: float = field(default=0.0, metadata={"range": (-1.0, 1.0)})
    legend_dy: float = field(default=0.0, metadata={"range": (-1.0, 1.0)})
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
    ("best", _("Automática")),
    ("upper right", _("Superior direita")),
    ("upper left", _("Superior esquerda")),
    ("lower right", _("Inferior direita")),
    ("lower left", _("Inferior esquerda")),
    ("center right", _("Centro direita")),
    ("outside", _("Fora (direita)")),
)

# Only the band and PDOS modules offer it (it is not in COMMON_FIELDS): a gap needs a spectrum.
LEGEND_GAP_FIELD = ParamField(
    "legend_gap",
    _("Gap de energia na legenda"),
    "legend",
    "bool",
    tooltip=_("Mostra o gap (CBM − VBM) na legenda. Sem efeito em sistema metálico."),
    requires="show_legend",
)

# How the gap of the legend and the footer is found (spec 34); only the band and PDOS modules.
GAP_METHODS = (
    ("auto", _("Automático")),
    ("homo_lumo", _("HOMO/LUMO do SCF")),
    ("janela", _("Maior intervalo na janela")),
)
GAP_METHOD_FIELD = ParamField(
    "gap_method",
    _("Método do gap"),
    "legend",
    "choice",
    choices=GAP_METHODS,
    tooltip=_(
        "Automático: nas bandas, pela contagem de elétrons; na PDOS, pelo HOMO/LUMO impresso "
        "ou pela DOS total perto de E_F.\n"
        "HOMO/LUMO do SCF: o par que o pw.x imprime (só com ocupações fixas e nbnd maior que as "
        "bandas ocupadas).\n"
        "Maior intervalo na janela: o maior vazio de pelo menos 0,05 eV entre as energias visíveis; "
        "muda com E mín e E máx."
    ),
    requires="legend_gap",
)


def gap_method_in_force(params: CommonParams) -> str:
    """The gap method that applies: the chosen one only while the gap is in the legend (the field
    does nothing without ``legend_gap``), else ``auto``; an unknown stored value is ``auto`` too."""
    method = getattr(params, "gap_method", "auto")
    known = method in (value for value, _label in GAP_METHODS)
    return method if known and getattr(params, "legend_gap", False) else "auto"


COMMON_FIELDS = (
    ParamField("line_width", _("Espessura"), "style", "float", minimum=0.1, maximum=6, step=0.1),
    ParamField("show_legend", _("Mostrar legenda"), "legend", "bool"),
    ParamField("legend_loc", _("Posição"), "legend", "choice", choices=LEGEND_LOCATIONS),
    ParamField(
        "legend_dx",
        "dx",
        "legend",
        "float",
        minimum=-1,
        maximum=1,
        step=0.05,
        tooltip=_(
            "Deslocamento horizontal da legenda, em fração da largura do gráfico (positivo: "
            "direita). Com a posição Automática, qualquer deslocamento usa Superior direita."
        ),
        requires="show_legend",
    ),
    ParamField(
        "legend_dy",
        "dy",
        "legend",
        "float",
        minimum=-1,
        maximum=1,
        step=0.05,
        tooltip=_(
            "Deslocamento vertical da legenda, em fração da altura do gráfico (positivo: "
            "cima). Com a posição Automática, qualquer deslocamento usa Superior direita."
        ),
        requires="show_legend",
    ),
    ParamField("legend_frame", _("Moldura"), "legend", "bool"),
    ParamField(
        "legend_size",
        _("Tamanho"),
        "legend",
        "float",
        minimum=4,
        maximum=40,
        step=1,
        suffix="pt",
        optional=True,
        tooltip=_("Tamanho do texto da legenda. Automático = 85 % da fonte da figura."),
    ),
    ParamField(
        "legend_transparency",
        _("Transparência"),
        "legend",
        "float",
        minimum=0,
        maximum=1,
        step=0.05,
        tooltip=_("0 = fundo da legenda opaco, 1 = invisível. Vale com a moldura ligada."),
    ),
    ParamField(
        "tick_size",
        _("Marcações"),
        "legend",
        "float",
        minimum=4,
        maximum=40,
        step=1,
        suffix="pt",
        optional=True,
        tooltip=_("Tamanho dos números nas marcações dos eixos. Automático = fonte da figura."),
    ),
    ParamField(
        "label_size",
        _("Rotulagem dos eixos"),
        "legend",
        "float",
        minimum=4,
        maximum=40,
        step=1,
        suffix="pt",
        optional=True,
        tooltip=_("Tamanho dos rótulos dos eixos. Automático = fonte da figura."),
    ),
    ParamField("title", _("Título"), "figure", "text"),
    ParamField(
        "figure_width",
        _("Largura"),
        "figure",
        "float",
        minimum=1,
        maximum=30,
        step=0.5,
        suffix="in",
    ),
    ParamField(
        "figure_height",
        _("Altura"),
        "figure",
        "float",
        minimum=1,
        maximum=30,
        step=0.5,
        suffix="in",
    ),
    ParamField(
        "font_size", _("Fonte"), "figure", "float", minimum=5, maximum=30, step=1, suffix="pt"
    ),
    ParamField("background", _("Cor de fundo"), "figure", "color", refreshes=True),
    ParamField("export_png", _("PNG"), "export", "bool"),
    ParamField("export_svg", _("SVG"), "export", "bool"),
    ParamField("export_pdf", _("PDF"), "export", "bool"),
    ParamField(
        "export_dpi",
        _("Resolução PNG"),
        "export",
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
