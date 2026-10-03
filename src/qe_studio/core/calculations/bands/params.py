"""Band plot parameters, their defaults and the tuning-panel schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..params import COMMON_FIELDS, CommonParams, ParamField, apply_common_config

if TYPE_CHECKING:
    from ...config import AppConfig
    from .data import BandsDataset

REFERENCES = (
    ("fermi", "E_F (SCF)"),
    ("vbm", "Topo da valência (VBM)"),
    ("midgap", "Meio do gap"),
    ("absolute", "Absoluta"),
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


SPIN_CHANNELS = (("both", "Ambos"), ("up", "Só ↑"), ("down", "Só ↓"))
SPIN_LAYOUTS = (("overlay", "Sobrepostos"), ("side", "Lado a lado"))
SPIN_COLORINGS = (("channel", "Canal"), ("occupation", "Valência/condução"))


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
            "Referência",
            "Energia",
            "choice",
            choices=tuple(references),
            refreshes=True,
        ),
        ParamField(
            "emin",
            "E mín",
            "Energia",
            "float",
            minimum=-1e4,
            maximum=1e4,
            step=0.5,
            decimals=3,
            suffix="eV",
        ),
        ParamField(
            "emax",
            "E máx",
            "Energia",
            "float",
            minimum=-1e4,
            maximum=1e4,
            step=0.5,
            decimals=3,
            suffix="eV",
        ),
        ParamField("show_fermi_line", "Linha de Fermi", "Energia", "bool"),
        ParamField(
            "xmin",
            "x mín",
            "Eixo X",
            "float",
            minimum=0,
            maximum=1e4,
            step=0.05,
            decimals=4,
            optional=True,
        ),
        ParamField(
            "xmax",
            "x máx",
            "Eixo X",
            "float",
            minimum=0,
            maximum=1e4,
            step=0.05,
            decimals=4,
            optional=True,
        ),
        ParamField(
            "labels",
            "Rótulos k",
            "Eixo X",
            "labels",
            tooltip="Separados por vírgula, ex.: G, X, W, L, G (G = Γ)",
        ),
        ParamField("show_hs_lines", "Linhas de alta simetria", "Eixo X", "bool"),
        ParamField("valence_color", "Valência", "Estilo", "color"),
        ParamField("conduction_color", "Condução", "Estilo", "color"),
        ParamField("fermi_color", "Fermi", "Estilo", "color"),
        *(_spin_fields() if dataset.spin else []),
        *COMMON_FIELDS,
    ]


def _spin_fields() -> list[ParamField]:
    return [
        ParamField("spin_channels", "Canais", "Spin", "choice", choices=SPIN_CHANNELS),
        ParamField("spin_layout", "Disposição", "Spin", "choice", choices=SPIN_LAYOUTS),
        ParamField("spin_coloring", "Cores por", "Spin", "choice", choices=SPIN_COLORINGS),
        ParamField("up_color", "Cor ↑", "Spin", "color"),
        ParamField("down_color", "Cor ↓", "Spin", "color"),
    ]


def param_changed(dataset: BandsDataset, params: BandsParams, name: str, old: Any) -> None:
    """Keep the visible absolute window when the energy reference changes."""
    if name == "reference":
        shift = dataset.reference(old) - dataset.reference(params.reference)
        params.emin += shift
        params.emax += shift
