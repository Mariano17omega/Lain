"""PDOS plot parameters, their defaults and the tuning-panel schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ....i18n import _
from ..params import (
    COMMON_FIELDS,
    GAP_METHOD_FIELD,
    LEGEND_GAP_FIELD,
    MID_GAP_TOOLTIP,
    CommonParams,
    ParamField,
    apply_common_config,
    style_field,
)

if TYPE_CHECKING:
    from ...config import AppConfig
    from .data import PdosDataset

# The code's colors of the orbitals and of each element (by the species label of the output), under
# those of the default plot style (``plot_styles/padrao.yaml``, spec 82): a style's map is added to
# these, never replaces them whole.
DEFAULT_ORBITAL_COLORS: dict[str, str] = {
    "s": "#fbbf24",
    "p": "#06b6d4",
    "d": "#a855f7",
    "f": "#ec4899",
}
DEFAULT_ATOMOS_COLORS: dict[str, str] = {
    "Al": "#E41A1C",
    "C": "#377EB8",
    "H": "#4DAF4A",
    "Hg": "#FF7F00",
    "K": "#984EA3",
    "O": "#228B22",
    "Si": "#F781BF",
}

GROUPINGS = (
    ("species_orbital", _("Espécie + orbital")),
    ("species", _("Espécie")),
    ("orbital", _("Orbital")),
)
ORIENTATIONS = (("horizontal", _("Energia no eixo x")), ("vertical", _("Energia no eixo y")))
# The field's own range: the toolbar stores this limit too, and a negative one flips the axis.
DOS_MAX_RANGE = (0.0, 1e6)
SPIN_MODES = (
    ("mirror", _("Espelhado (↓ negativo)")),
    ("overlay", _("Sobreposto")),
    ("up", _("Só ↑")),
    ("down", _("Só ↓")),
    ("sum", _("Soma (↑ + ↓)")),
)


@dataclass
class PdosParams(CommonParams):
    # Not always offered (``_source_matters``), so the metadata says how to validate a stored value.
    fermi_source: str = field(
        default="scf", metadata={"kind": "choice", "choices": ("scf", "nscf")}
    )
    shift_to_fermi: bool = True
    emin: float = -5.0
    emax: float = 5.0
    dos_max: float | None = field(default=None, metadata={"range": DOS_MAX_RANGE})
    grouping: str = "species_orbital"
    orientation: str = "horizontal"
    show_total: bool = True
    total_color: str = field(default="", metadata={"kind": "color"})  # empty = theme text color
    fill_occupied: bool = True
    show_fermi_line: bool = True
    fermi_color: str = field(default="#f43f5e", metadata={"kind": "color"})
    # 1-based atoms shown, None = all. Kept per compound in the user's CompoundStore, never in the
    # (per-folder) .plot: see ``stored_elsewhere``.
    atoms: list[int] | None = field(default=None, metadata={"store": "compound"})
    hidden_series: list[str] = field(default_factory=list)
    series_colors: dict[str, str] = field(default_factory=dict)
    orbital_colors: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ORBITAL_COLORS),
        metadata={"kind": "colors", "keys": tuple(DEFAULT_ORBITAL_COLORS)},  # s, p, d, f only
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
    )
    params.fermi_source = "scf" if dataset.fermi_scf is not None else "nscf"
    if (
        not params.shift_to_fermi
        and (fermi := dataset.fermi_level(params.fermi_source)) is not None
    ):
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
        *(
            [
                ParamField(
                    "fermi_source",
                    _("E_F de"),
                    "energy",
                    "choice",
                    choices=tuple(sources),
                    refreshes=True,
                )
            ]
            if _source_matters(dataset)
            else []
        ),
        ParamField(
            "shift_to_fermi",
            _("Referenciar a E_F"),
            "energy",
            "bool",
            refreshes=True,
            tooltip=MID_GAP_TOOLTIP,
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
        ParamField("orientation", _("Orientação"), "x_axis", "choice", choices=ORIENTATIONS),
        ParamField(
            "dos_max",
            _("DOS máx"),
            "x_axis",
            "float",
            minimum=DOS_MAX_RANGE[0],
            maximum=DOS_MAX_RANGE[1],
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
        style_field(),
        ParamField("fermi_color", _("Fermi"), "style", "color"),
        *COMMON_FIELDS,
        LEGEND_GAP_FIELD,
        GAP_METHOD_FIELD,
    ]


def _source_matters(dataset: PdosDataset) -> bool:
    """Can "E_F de" change the plot? An insulator's E_F is the middle of its gap whichever run is
    asked, unless one of the runs keeps an E_F per channel."""
    if dataset.proven_midgap is None:
        return True
    return dataset.fermi_level("scf") != dataset.fermi_level("nscf")


def param_changed(dataset: PdosDataset, params: PdosParams, name: str, old: Any) -> None:
    """Keep the visible absolute window when the energy reference changes."""
    if name in ("shift_to_fermi", "fermi_source"):
        before = reference(dataset, params, **{name: old})
        after = reference(dataset, params)
        params.emin += before - after
        params.emax += before - after


def reference(dataset: PdosDataset, params: PdosParams, **override) -> float:
    """The energy the plot is measured from: E_F of the chosen run, or 0 (absolute energies)."""
    shift = override.get("shift_to_fermi", params.shift_to_fermi)
    source = override.get("fermi_source", params.fermi_source)
    fermi = dataset.fermi_level(source)
    return fermi if shift and fermi is not None else 0.0


def is_shifted(dataset: PdosDataset, params: PdosParams) -> bool:
    """Whether the energies are measured from E_F (an E_F of exactly 0.0 is still a shift)."""
    return params.shift_to_fermi and dataset.fermi(params.fermi_source) is not None
