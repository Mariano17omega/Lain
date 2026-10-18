"""PDOS plot parameters, their defaults and the tuning-panel schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ....i18n import _
from ...config import DEFAULT_ATOMOS_COLORS, DEFAULT_ORBITAL_COLORS
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
    from .data import PdosDataset

GROUPINGS = (
    ("species_orbital", _("Espécie + orbital")),
    ("species", _("Espécie")),
    ("orbital", _("Orbital")),
)
ORIENTATIONS = (("horizontal", _("Energia no eixo x")), ("vertical", _("Energia no eixo y")))
SPIN_MODES = (
    ("mirror", _("Espelhado (↓ negativo)")),
    ("overlay", _("Sobreposto")),
    ("up", _("Só ↑")),
    ("down", _("Só ↓")),
    ("sum", _("Soma (↑ + ↓)")),
)


@dataclass
class PdosParams(CommonParams):
    fermi_source: str = "scf"
    shift_to_fermi: bool = True
    emin: float = -5.0
    emax: float = 5.0
    dos_max: float | None = None
    grouping: str = "species_orbital"
    orientation: str = "horizontal"
    show_total: bool = True
    total_color: str = field(default="", metadata={"kind": "color"})  # empty = theme text color
    fill_occupied: bool = True
    show_fermi_line: bool = True
    fermi_color: str = "#f43f5e"
    # 1-based atoms shown, None = all. Kept per compound in the user's CompoundStore, never in the
    # (per-folder) .plot: see ``stored_elsewhere``.
    atoms: list[int] | None = field(default=None, metadata={"store": "compound"})
    hidden_series: list[str] = field(default_factory=list)
    series_colors: dict[str, str] = field(default_factory=dict)
    orbital_colors: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ORBITAL_COLORS), metadata={"kind": "colors"}
    )
    atomos_colors: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ATOMOS_COLORS), metadata={"kind": "colors"}
    )
    show_legend: bool = True
    legend_gap: bool = False  # the energy gap as a legend entry
    gap_method: str = "auto"  # how that gap is found (needs legend_gap): GAP_METHODS
    spin_mode: str = "mirror"  # only offered (and used) when the PDOS has two channels


def default_params(config: AppConfig, dataset: PdosDataset) -> PdosParams:
    plot = config.plot
    params = PdosParams(
        shift_to_fermi=plot.shift_to_fermi and dataset.fermi("scf") is not None,
        emin=plot.energy_min,
        emax=plot.energy_max,
        fermi_color=plot.fermi_color,
        orbital_colors={orbital: color for orbital, color in plot.orbital_colors.items()},
        atomos_colors=dict(plot.atomos_colors),
    )
    params.fermi_source = "scf" if dataset.fermi_scf is not None else "nscf"
    if not params.shift_to_fermi and (fermi := dataset.fermi(params.fermi_source)) is not None:
        params.emin += fermi
        params.emax += fermi
    apply_common_config(params, config)
    params.show_legend = True
    return params


def param_schema(dataset: PdosDataset) -> list[ParamField]:
    sources = [("scf", _("SCF"))] if dataset.fermi_scf is not None else []
    if dataset.fermi_nscf is not None:
        sources.append(("nscf", "NSCF"))
    return [
        ParamField(
            "fermi_source",
            _("E_F de"),
            "energy",
            "choice",
            choices=tuple(sources),
            refreshes=True,
        ),
        ParamField("shift_to_fermi", _("Referenciar a E_F"), "energy", "bool", refreshes=True),
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
        ParamField("orientation", _("Orientação"), "x_axis", "choice", choices=ORIENTATIONS),
        ParamField(
            "dos_max",
            _("DOS máx"),
            "x_axis",
            "float",
            minimum=0,
            maximum=1e6,
            step=0.5,
            decimals=2,
            suffix="est./eV",
            optional=True,
        ),
        ParamField(
            "grouping",
            _("Agrupar por"),
            "projections",
            "choice",
            choices=GROUPINGS,
            refreshes=True,
        ),
        ParamField("show_total", _("DOS total"), "projections", "bool"),
        ParamField("fill_occupied", _("Preencher estados ocupados"), "projections", "bool"),
        ParamField("atoms", _("Átomos"), "projections", "atoms"),
        *(
            [ParamField("spin_mode", _("Spin"), "projections", "choice", choices=SPIN_MODES)]
            if dataset.data.spin_polarized
            else []
        ),
        ParamField("hidden_series", _("Séries"), "projections", "series", colors="series_colors"),
        ParamField("fermi_color", _("Fermi"), "style", "color"),
        *COMMON_FIELDS,
        LEGEND_GAP_FIELD,
        GAP_METHOD_FIELD,
    ]


def param_changed(dataset: PdosDataset, params: PdosParams, name: str, old: Any) -> None:
    """Keep the visible absolute window when the energy reference changes."""
    if name in ("shift_to_fermi", "fermi_source"):
        before = reference(dataset, params, **{name: old})
        after = reference(dataset, params)
        params.emin += before - after
        params.emax += before - after


def reference(dataset: PdosDataset, params: PdosParams, **override) -> float:
    shift = override.get("shift_to_fermi", params.shift_to_fermi)
    source = override.get("fermi_source", params.fermi_source)
    fermi = dataset.fermi(source)
    return fermi if shift and fermi is not None else 0.0
