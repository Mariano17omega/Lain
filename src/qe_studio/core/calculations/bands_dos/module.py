"""Bands + DOS in one figure (spec 22): a module built from two folders' results, never detected.

``pair.pair_result`` makes its ``DetectionResult`` (the bands folder's, with the band and PDOS
results as ``parts``); ``detection.PairTarget`` does it in the load worker from two folders.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from matplotlib.figure import FigureBase

from ...compounds import AtomChoices
from ...plotting.style import PlotStyle
from ..bands import BandsModule
from ..base import AxesLimits, CalculationModule, DetectionResult, FileRole, SniffFn, Stores
from ..params import ParamField, RenderInfo
from ..pdos import PdosModule
from ..pdos import atoms as pdos_atoms
from ..pdos import render as pdos_render
from . import params as params_mod
from . import render as render_mod
from .data import BandsDosDataset, load_dataset
from .pair import PARTS
from .params import BandsDosParams, dos_view

if TYPE_CHECKING:
    from ...config import AppConfig


def _prefixed(roles: tuple[FileRole, ...], prefix: str, label: str) -> tuple[FileRole, ...]:
    """A part's roles as this module lists them (the panel's "Arquivos"): never an anchor."""
    return tuple(
        replace(r, id=f"{prefix}.{r.id}", label=f"{label} · {r.label}", anchor=False) for r in roles
    )


class BandsDosModule(CalculationModule[BandsDosDataset, BandsDosParams]):
    kind: ClassVar[str] = "bands_dos"
    badge: ClassVar[str] = "BANDS+DOS"
    display_name: ClassVar[str] = "Bandas + DOS"
    description: ClassVar[str] = (
        "Estrutura de bandas e PDOS de duas pastas, com o mesmo eixo de energia"
    )
    plottable: ClassVar[bool] = True
    selectable: ClassVar[bool] = False  # made from two folders, not mapped from one
    view_fields: ClassVar[tuple[str, ...]] = ("emin", "emax", "xmin", "xmax", "dos_max")
    sections: ClassVar[tuple[tuple[str, str | None], ...]] = params_mod.SECTIONS
    roles: ClassVar[tuple[FileRole, ...]] = _prefixed(BandsModule.roles, *PARTS[0]) + _prefixed(
        PdosModule.roles, *PARTS[1]
    )

    # -- plotting ------------------------------------------------------------------------------
    def load(self, result: DetectionResult, sniff: SniffFn) -> BandsDosDataset:
        return load_dataset(result, sniff)

    def default_params(self, config: AppConfig, dataset: BandsDosDataset) -> BandsDosParams:
        return params_mod.default_params(config, dataset)

    def param_schema(self, dataset: BandsDosDataset) -> list[ParamField]:
        return params_mod.param_schema(dataset)

    def param_changed(
        self, dataset: BandsDosDataset, params: BandsDosParams, name: str, old: Any
    ) -> None:
        params_mod.param_changed(dataset, params, name, old)

    def plot_title(self, target: Path, dataset: BandsDosDataset) -> str:
        formula = dataset.bands.formula or (dataset.dos.compound and dataset.dos.compound.formula)
        return f"{self.display_name} — {formula or target.name}"

    def render(
        self, figure: FigureBase, dataset: BandsDosDataset, params: BandsDosParams, style: PlotStyle
    ) -> RenderInfo:
        return render_mod.render_bands_dos(figure, dataset, params, style)

    # -- view hooks ----------------------------------------------------------------------------
    def apply_limits(self, params: BandsDosParams, axes_limits: AxesLimits) -> None:
        """Axes 0 (bands): k and the shared energy; axes 1 (DOS): its density limit."""
        (xlim, ylim), (dos_lim, _ylim) = axes_limits[0], axes_limits[1]
        params.emin, params.emax = ylim
        params.xmin, params.xmax = xlim
        mirrored = params.spin_mode == "mirror"
        params.dos_max = max(abs(dos_lim[0]), abs(dos_lim[1])) if mirrored else dos_lim[1]

    def format_coordinates(
        self, x: float, y: float, axes_index: int, dataset: BandsDosDataset, params: BandsDosParams
    ) -> str:
        return render_mod.format_coordinates(x, y, axes_index, dataset, params)

    def default_labels(self, dataset: BandsDosDataset) -> list[str]:
        return list(dataset.bands.labels)

    def series_colors(
        self, dataset: BandsDosDataset, params: BandsDosParams, style: PlotStyle
    ) -> dict[str, str]:
        return pdos_render.series_colors(dataset.dos, dos_view(params), style)

    # -- the atoms of the DOS, saved per compound (spec 21) ------------------------------------
    def atoms_of(self, dataset: BandsDosDataset) -> AtomChoices:
        return pdos_atoms.atoms_of(dataset.dos)

    def stored_params(self, dataset: BandsDosDataset, stores: Stores) -> dict[str, Any]:
        return pdos_atoms.stored_params(dataset.dos, stores)

    def save_stored(
        self, dataset: BandsDosDataset, params: BandsDosParams, name: str, stores: Stores
    ) -> None:
        pdos_atoms.save_stored(dataset.dos, dos_view(params), name, stores)
