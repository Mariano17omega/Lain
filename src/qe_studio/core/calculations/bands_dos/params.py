"""Bands + DOS parameters: the shared energy axis, the band panel's and the DOS panel's (spec 22).

The figure draws each panel with the band and PDOS code, so ``bands_view`` / ``dos_view`` turn these
parameters into theirs. The panel schema is theirs too, picked by name and moved into the sections
of this figure: the shared ones keep their names, the ones of a single panel are prefixed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from typing import TYPE_CHECKING, Any, TypeVar

from ...config import DEFAULT_ORBITAL_COLORS
from ..bands import params as bands_params
from ..bands.params import BandsParams
from ..params import COMMON_FIELDS, LEGEND_GAP_FIELD, CommonParams, ParamField
from ..pdos import params as pdos_params
from ..pdos.params import PdosParams

if TYPE_CHECKING:
    from ...config import AppConfig
    from .data import BandsDosDataset

T = TypeVar("T")

BANDS_AXIS = "Bandas ▸ Eixo k"
BANDS_COLORS = "Bandas ▸ Cores"
BANDS_SPIN = "Bandas ▸ Spin"
DOS_AXIS = "DOS ▸ Eixo"
DOS_PROJECTIONS = "DOS ▸ Projeções"
# The module's own sections, all ahead of "Estilo" in this order (``ordered_sections``).
SECTIONS = tuple(
    (name, "Estilo") for name in (BANDS_AXIS, BANDS_COLORS, BANDS_SPIN, DOS_AXIS, DOS_PROJECTIONS)
)


@dataclass
class BandsDosParams(CommonParams):
    # The shared energy axis: the bands' reference, applied to both panels.
    reference: str = "fermi"
    emin: float = -5.0
    emax: float = 5.0
    show_fermi_line: bool = True
    fermi_color: str = "#f43f5e"
    # The band panel.
    xmin: float | None = None
    xmax: float | None = None
    labels: str = ""
    show_hs_lines: bool = True
    valence_color: str = "#2563eb"
    conduction_color: str = "#00d2ff"
    spin_channels: str = "both"
    spin_coloring: str = "channel"
    up_color: str = field(default="#2563eb", metadata={"kind": "color"})
    down_color: str = field(default="#f97316", metadata={"kind": "color"})
    # The DOS panel.
    dos_width_ratio: float = 0.35  # of the band panel's width
    dos_max: float | None = None
    grouping: str = "species_orbital"
    show_total: bool = True
    total_color: str = field(default="", metadata={"kind": "color"})
    fill_occupied: bool = True
    atoms: list[int] | None = field(default=None, metadata={"store": "compound"})
    hidden_series: list[str] = field(default_factory=list)
    series_colors: dict[str, str] = field(default_factory=dict)
    orbital_colors: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ORBITAL_COLORS), metadata={"kind": "colors"}
    )
    spin_mode: str = "overlay"  # mirrored makes the DOS axis symmetric, odd next to the bands
    show_legend: bool = True
    legend_gap: bool = False
    # The DOS folder relative to the bands folder, for whoever reads bands_dos.plot (reopening the
    # figure from it): set from the data, never read back (plot_file.derived_fields).
    dos_folder: str = field(default="", metadata={"kind": "text", "derived": True})


def _shared(source: Any, cls: type) -> dict[str, Any]:
    """The values of ``source`` for the fields ``cls`` has too."""
    return {f.name: getattr(source, f.name) for f in fields(cls) if hasattr(source, f.name)}


def bands_view(params: BandsDosParams) -> BandsParams:
    """The band panel's parameters (its two spin channels always overlaid)."""
    return BandsParams(**_shared(params, BandsParams), spin_layout="overlay")


def dos_view(params: BandsDosParams) -> PdosParams:
    """The DOS panel's parameters: energy on Y, in the window of the shared axis."""
    return PdosParams(**_shared(params, PdosParams), orientation="vertical")


def default_params(config: AppConfig, dataset: BandsDosDataset) -> BandsDosParams:
    """Each panel's defaults (the bands' win on shared names), the DOS overlaid and a legend."""
    bands = bands_params.default_params(config, dataset.bands)
    dos = pdos_params.default_params(config, dataset.dos)
    params = BandsDosParams(**{**_shared(dos, BandsDosParams), **_shared(bands, BandsDosParams)})
    params.spin_mode = "overlay"
    params.show_legend = True
    params.legend_loc = "outside"  # inside, it would cover the narrow DOS panel
    params.dos_folder = relative_folder(dataset.dos.folder, dataset.bands.folder)
    return params


def relative_folder(folder: os.PathLike[str], start: os.PathLike[str]) -> str:
    return os.path.relpath(folder, start).replace(os.sep, "/")


WIDTH_FIELD = ParamField(
    "dos_width_ratio",
    "Largura da DOS",
    DOS_AXIS,
    "float",
    minimum=0.1,
    maximum=2.0,
    step=0.05,
    decimals=2,
    tooltip="Largura do painel da DOS em relação ao das bandas",
)


def param_schema(dataset: BandsDosDataset) -> list[ParamField]:
    bands = {f.name: f for f in bands_params.param_schema(dataset.bands)}
    dos = {f.name: f for f in pdos_params.param_schema(dataset.dos)}

    def take(source: dict[str, ParamField], names: tuple[str, ...], section: str):
        return [replace(source[name], section=section) for name in names if name in source]

    return [
        *take(bands, ("reference", "emin", "emax", "show_fermi_line"), "Energia"),
        *take(bands, ("xmin", "xmax", "labels", "show_hs_lines"), BANDS_AXIS),
        *take(bands, ("valence_color", "conduction_color"), BANDS_COLORS),
        *take(bands, ("spin_channels", "spin_coloring", "up_color", "down_color"), BANDS_SPIN),
        WIDTH_FIELD,
        *take(dos, ("dos_max",), DOS_AXIS),
        *take(
            dos,
            ("grouping", "show_total", "fill_occupied", "atoms", "spin_mode", "hidden_series"),
            DOS_PROJECTIONS,
        ),
        *take(bands, ("fermi_color",), "Estilo"),
        *COMMON_FIELDS,
        LEGEND_GAP_FIELD,
    ]


def param_changed(dataset: BandsDosDataset, params: BandsDosParams, name: str, old: Any) -> None:
    """Keep the visible absolute window when the energy reference changes."""
    if name == "reference":
        shift = dataset.bands.reference(old) - dataset.bands.reference(params.reference)
        params.emin += shift
        params.emax += shift
