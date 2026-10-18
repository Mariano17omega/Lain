"""Band plot parameters, their defaults and the tuning-panel schema."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from ....i18n import _
from ..params import (
    COMMON_FIELDS,
    GAP_METHOD_FIELD,
    LEGEND_GAP_FIELD,
    CommonParams,
    ParamField,
    apply_common_config,
)

if TYPE_CHECKING:
    from ...config import AppConfig
    from .data import BandsDataset

# The bands' gap is the one along the path (spec 27-6 R1.3); bands + DOS shows the same gap.
BANDS_LEGEND_GAP_FIELD = replace(
    LEGEND_GAP_FIELD,
    tooltip=_(
        "{tooltip} Gap ao longo do caminho de k; o gap indireto verdadeiro pode estar fora dele."
    ).format(tooltip=LEGEND_GAP_FIELD.tooltip),
)

REFERENCES = (
    ("fermi", _("E_F (SCF)")),
    ("vbm", _("Topo da valência (VBM)")),
    ("midgap", _("Meio do gap")),
    ("absolute", _("Absoluta")),
)
ENERGY_NAMES = {  # plain text of Y_LABELS, for the cursor readout
    "fermi": "E − E_F",
    "vbm": "E − E_VBM",
    "midgap": "E − E_gap/2",
    "absolute": "E",
}
Y_LABELS = {
    "fermi": r"$E - E_F$ (eV)",
    "vbm": r"$E - E_{VBM}$ (eV)",
    "midgap": r"$E - E_{gap/2}$ (eV)",
    "absolute": r"$E$ (eV)",
}


SPIN_CHANNELS = (("both", _("Ambos")), ("up", _("Só ↑")), ("down", _("Só ↓")))
SPIN_LAYOUTS = (("overlay", _("Sobrepostos")), ("side", _("Lado a lado")))
SPIN_COLORINGS = (("channel", _("Canal")), ("occupation", _("Valência/condução")))


@dataclass
class BandsParams(CommonParams):
    reference: str = "fermi"
    emin: float = -5.0
    emax: float = 5.0
    xmin: float | None = None
    xmax: float | None = None
    labels: str = ""  # comma-separated override; empty = labels from the input file
    show_hs_lines: bool = True
    show_fermi_line: bool = True
    valence_color: str = "#2563eb"
    conduction_color: str = "#00d2ff"
    fermi_color: str = "#f43f5e"
    legend_gap: bool = False  # the energy gap as a legend entry (needs show_legend)
    gap_method: str = "auto"  # how that gap is found (needs legend_gap): GAP_METHODS
    # Spin (only offered when the dataset has two channels). No schema field without spin, so the
    # colors say how to validate a stored value.
    spin_channels: str = "both"
    spin_layout: str = "overlay"
    spin_coloring: str = "channel"
    up_color: str = field(default="#2563eb", metadata={"kind": "color"})
    down_color: str = field(default="#f97316", metadata={"kind": "color"})


def default_params(config: AppConfig, dataset: BandsDataset) -> BandsParams:
    plot = config.plot
    params = BandsParams(
        reference="fermi" if plot.shift_to_fermi and dataset.fermi is not None else "absolute",
        emin=plot.energy_min,
        emax=plot.energy_max,
        valence_color=plot.band_colors.valence,
        conduction_color=plot.band_colors.conduction,
        fermi_color=plot.fermi_color,
    )
    if params.reference == "absolute" and dataset.fermi is not None:
        params.emin += dataset.fermi
        params.emax += dataset.fermi
    apply_common_config(params, config)
    return params


def param_schema(dataset: BandsDataset) -> list[ParamField]:
    references = [
        (value, label)
        for value, label in REFERENCES
        if value == "absolute"
        or (value == "fermi" and dataset.fermi is not None)
        or (value in ("vbm", "midgap") and dataset.gap is not None)
    ]
    return [
        ParamField(
            "reference",
            _("Referência"),
            "energy",
            "choice",
            choices=tuple(references),
            refreshes=True,
        ),
        ParamField(
            "emin",
            _("E mín"),
            "energy",
            "float",
            minimum=-1e4,
            maximum=1e4,
            step=0.5,
            decimals=3,
            suffix="eV",
        ),
        ParamField(
            "emax",
            _("E máx"),
            "energy",
            "float",
            minimum=-1e4,
            maximum=1e4,
            step=0.5,
            decimals=3,
            suffix="eV",
        ),
        ParamField("show_fermi_line", _("Linha de Fermi"), "energy", "bool"),
        ParamField(
            "xmin",
            _("x mín"),
            "x_axis",
            "float",
            minimum=0,
            maximum=1e4,
            step=0.05,
            decimals=4,
            optional=True,
        ),
        ParamField(
            "xmax",
            _("x máx"),
            "x_axis",
            "float",
            minimum=0,
            maximum=1e4,
            step=0.05,
            decimals=4,
            optional=True,
        ),
        ParamField(
            "labels",
            _("Rótulos k"),
            "x_axis",
            "labels",
            tooltip=_("Separados por vírgula, ex.: G, X, W, L, G (G = Γ)"),
        ),
        ParamField("show_hs_lines", _("Linhas de alta simetria"), "x_axis", "bool"),
        ParamField("valence_color", _("Valência"), "style", "color"),
        ParamField("conduction_color", _("Condução"), "style", "color"),
        ParamField("fermi_color", _("Fermi"), "style", "color"),
        *(_spin_fields() if dataset.spin else []),
        *COMMON_FIELDS,
        BANDS_LEGEND_GAP_FIELD,
        GAP_METHOD_FIELD,
    ]


def _spin_fields() -> list[ParamField]:
    return [
        ParamField("spin_channels", _("Canais"), "spin", "choice", choices=SPIN_CHANNELS),
        ParamField("spin_layout", _("Disposição"), "spin", "choice", choices=SPIN_LAYOUTS),
        ParamField("spin_coloring", _("Cores por"), "spin", "choice", choices=SPIN_COLORINGS),
        ParamField("up_color", _("Cor ↑"), "spin", "color"),
        ParamField("down_color", _("Cor ↓"), "spin", "color"),
    ]


def param_changed(dataset: BandsDataset, params: BandsParams, name: str, old: Any) -> None:
    """Keep the visible absolute window when the energy reference changes."""
    if name == "reference":
        shift = dataset.reference(old) - dataset.reference(params.reference)
        params.emin += shift
        params.emax += shift
