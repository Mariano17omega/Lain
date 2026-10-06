"""Projected density of states (PRD §4.3): the module that ties detection, data, params, render."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from matplotlib.figure import FigureBase

from ...compounds import AtomChoices
from ...plotting.style import PlotStyle
from ...qe import projwfc
from ...sniff import FileKind, FileSniff
from ..base import (
    AxesLimits,
    CalculationModule,
    DetectionResult,
    FileRole,
    FolderListing,
    SniffFn,
    Stores,
    output_of,
)
from ..params import ParamField, RenderInfo
from . import atoms as atoms_mod
from . import params as params_mod
from . import render as render_mod
from . import table as table_mod
from .data import PdosDataset, load_dataset
from .params import PdosParams

if TYPE_CHECKING:
    from ...config import AppConfig
    from ...plotting.table import PlotTable


def _group_key(path: Path) -> tuple[Path, str]:
    meta = projwfc.parse_atm_name(path.name)
    return path.parent, meta.prefix if meta else ""


def _newest(paths: list[Path]) -> float:
    try:
        return max(p.stat().st_mtime for p in paths)
    except OSError:
        return 0.0


class PdosModule(CalculationModule[PdosDataset, PdosParams]):
    kind: ClassVar[str] = "pdos"
    badge: ClassVar[str] = "PDOS"
    badge_token: ClassVar[str | None] = "pdos"
    view_fields: ClassVar[tuple[str, ...]] = ("emin", "emax", "dos_max")
    sections: ClassVar[tuple[tuple[str, str | None], ...]] = (("Projeções", "Legenda"),)
    display_name: ClassVar[str] = "Densidade de estados projetada"
    description: ClassVar[str] = "pdos_tot e arquivos de PDOS por átomo detectados"
    plottable: ClassVar[bool] = True
    has_table: ClassVar[bool] = True
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole("scf_out", "Saída SCF (pw.x)", output_of(FileKind.PW_OUT, "scf"), ("scf*.out",)),
        FileRole(
            "nscf_out", "Saída NSCF (pw.x)", output_of(FileKind.PW_OUT, "nscf"), ("nscf*.out",)
        ),
        FileRole(
            "projwfc_out",
            "Saída do projwfc.x",
            output_of(FileKind.PROJWFC_OUT),
            ("projwfc*.out",),
            anchor=True,
        ),
        FileRole(
            "pdos_atm",
            "Projeções pdos_atm#*_wfc#*",
            output_of(FileKind.PDOS_ATM),
            ("orbitals/*pdos_atm#*_wfc#*",),
            required=True,
            multiple=True,
            anchor=True,
        ),
        FileRole(
            "pdos_tot",
            "DOS total (pdos_tot)",
            output_of(FileKind.PDOS_TOT),
            ("*pdos_tot", "orbitals/*pdos_tot"),
        ),
    )

    # -- detection -----------------------------------------------------------------------------
    def select(
        self,
        role: FileRole,
        candidates: list[Path],
        sniffs: dict[Path, FileSniff],
        result: DetectionResult,
    ) -> list[Path]:
        if role.id == "pdos_atm":
            groups: dict[tuple[Path, str], list[Path]] = {}
            for path in candidates:
                groups.setdefault(_group_key(path), []).append(path)
            chosen = max(groups.values(), key=_newest)
            if len(groups) > 1:
                result.warnings.append(
                    f"{len(groups)} conjuntos de PDOS encontrados; usando o mais recente "
                    f"({_group_key(chosen[0])[1] or chosen[0].parent.name})"
                )
            return sorted(chosen)
        if role.id == "pdos_tot" and "pdos_atm" in result.files:
            prefix = _group_key(result.files["pdos_atm"][0])[1]
            same = [p for p in candidates if p.name.removesuffix("pdos_tot").rstrip(".") == prefix]
            if same:
                candidates = same
        return super().select(role, candidates, sniffs, result)

    def finalize(
        self,
        result: DetectionResult,
        listing: FolderListing,
        sniffs: dict[Path, FileSniff],
        sniff: SniffFn,
    ) -> None:
        self.infer_from_neighbours(result, "scf_out", sniff)
        if "scf_out" not in result.files and "nscf_out" not in result.files:
            result.missing.append("scf_out")
        elif "scf_out" not in result.files:
            result.warnings.append("saída SCF não encontrada: E_F lida da saída NSCF")

    # -- plotting ------------------------------------------------------------------------------
    def default_params(self, config: AppConfig, dataset: PdosDataset) -> PdosParams:
        return params_mod.default_params(config, dataset)

    def param_schema(self, dataset: PdosDataset) -> list[ParamField]:
        return params_mod.param_schema(dataset)

    def param_changed(self, dataset: PdosDataset, params: PdosParams, name: str, old: Any) -> None:
        params_mod.param_changed(dataset, params, name, old)

    def apply_limits(self, params: PdosParams, axes_limits: AxesLimits) -> None:
        xlim, ylim = axes_limits[0]
        energy, dos = (ylim, xlim) if params.orientation == "vertical" else (xlim, ylim)
        params.emin, params.emax = energy
        # Mirrored: the DOS axis is symmetric, so its limit is the larger side; else it starts at 0.
        params.dos_max = max(abs(dos[0]), abs(dos[1])) if params.spin_mode == "mirror" else dos[1]

    def table(self, dataset: PdosDataset, params: PdosParams) -> PlotTable:
        return table_mod.pdos_table(dataset, params)

    def format_coordinates(
        self, x: float, y: float, axes_index: int, dataset: PdosDataset, params: PdosParams
    ) -> str:
        return render_mod.format_coordinates(x, y, axes_index, dataset, params)

    def load(self, result: DetectionResult, sniff: SniffFn) -> PdosDataset:
        return load_dataset(result, sniff)

    def atoms_of(self, dataset: PdosDataset) -> AtomChoices:
        return atoms_mod.atoms_of(dataset)

    def stored_params(self, dataset: PdosDataset, stores: Stores) -> dict[str, Any]:
        return atoms_mod.stored_params(dataset, stores)

    def save_stored(
        self, dataset: PdosDataset, params: PdosParams, name: str, stores: Stores
    ) -> None:
        atoms_mod.save_stored(dataset, params, name, stores)

    def series_colors(
        self, dataset: PdosDataset, params: PdosParams, style: PlotStyle
    ) -> dict[str, str]:
        return render_mod.series_colors(dataset, params, style)

    def render(
        self, figure: FigureBase, dataset: PdosDataset, params: PdosParams, style: PlotStyle
    ) -> RenderInfo:
        return render_mod.render_pdos(figure, dataset, params, style)

    @staticmethod
    def summary(dataset: PdosDataset, params: PdosParams) -> str:
        return render_mod.summary(dataset, params)
