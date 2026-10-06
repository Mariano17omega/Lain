"""Electronic band structure (PRD §4.2): the module that ties detection, data, params and render."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from matplotlib.figure import FigureBase

from ...plotting.style import PlotStyle
from ...sniff import FileKind, FileSniff
from ..base import (
    AxesLimits,
    CalculationModule,
    DetectionResult,
    FileRole,
    FolderListing,
    SniffFn,
    output_of,
)
from ..params import ParamField, RenderInfo
from . import params as params_mod
from . import render as render_mod
from . import table as table_mod
from .data import BandsDataset, load_dataset
from .detection import assign_channels, check_bands, named_by_bandsx
from .params import BandsParams

if TYPE_CHECKING:
    from ...config import AppConfig
    from ...folder_memory import FolderMemory
    from ...plotting.table import PlotTable


class BandsModule(CalculationModule[BandsDataset, BandsParams]):
    kind: ClassVar[str] = "bands"
    badge: ClassVar[str] = "BANDS"
    badge_token: ClassVar[str | None] = "bands"
    view_fields: ClassVar[tuple[str, ...]] = ("emin", "emax", "xmin", "xmax")
    sections: ClassVar[tuple[tuple[str, str | None], ...]] = (("Spin", "Estilo"),)
    display_name: ClassVar[str] = "Estrutura de bandas"
    description: ClassVar[str] = "bands.x/.gnu detectados"
    plottable: ClassVar[bool] = True
    has_table: ClassVar[bool] = True
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole(
            "scf_out",
            "Saída SCF (pw.x)",
            output_of(FileKind.PW_OUT, "scf"),
            ("scf*.out",),
            required=True,
        ),
        FileRole(
            "bands_in",
            "Entrada de bandas (pw.x, calculation='bands')",
            output_of(FileKind.PW_IN, "bands"),
            ("bands*.in",),
            anchor=True,
        ),
        FileRole(
            "bands_out",
            "Saída de bandas (pw.x)",
            output_of(FileKind.PW_OUT, "bands"),
            ("bands*.out",),
            anchor=True,
        ),
        FileRole(
            "bandsx_in",
            "Entrada do bands.x",
            output_of(FileKind.BANDSX_IN),
            ("bands*.in", "*band*x*.in"),
            multiple=True,
        ),
        FileRole(
            "bandsx_out",
            "Saída do bands.x",
            output_of(FileKind.BANDSX_OUT),
            ("bands*.out",),
            anchor=True,
        ),
        FileRole("filband", "Dados de bandas (filband)", output_of(FileKind.FILBAND)),
        FileRole("filband_down", "Dados de bandas ↓ (filband)", output_of(FileKind.FILBAND)),
        FileRole(
            "gnu",
            "Dados de bandas (.gnu)",
            output_of(FileKind.GNU_DATA),
            ("*.gnu", "*.dat.gnu"),
            anchor=True,
        ),
        FileRole(
            "gnu_down",
            "Dados de bandas ↓ (.gnu)",
            output_of(FileKind.GNU_DATA),
            ("*.gnu", "*.dat.gnu"),
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
        if role.id.endswith("_down"):
            return []  # the ↓ files are paired with the ↑ ones in ``finalize``
        if role.id in ("gnu", "filband"):
            preferred = named_by_bandsx(role.id, candidates, sniffs, result)
            if preferred:
                return [preferred]
        return super().select(role, candidates, sniffs, result)

    def finalize(
        self,
        result: DetectionResult,
        listing: FolderListing,
        sniffs: dict[Path, FileSniff],
        sniff: SniffFn,
    ) -> None:
        self.infer_from_neighbours(result, "scf_out", sniff)
        assign_channels(result, listing, sniffs, sniff)
        check_bands(result, sniffs, sniff)

    # -- plotting ------------------------------------------------------------------------------
    def default_params(self, config: AppConfig, dataset: BandsDataset) -> BandsParams:
        return params_mod.default_params(config, dataset)

    def param_schema(self, dataset: BandsDataset) -> list[ParamField]:
        return params_mod.param_schema(dataset)

    def param_changed(
        self, dataset: BandsDataset, params: BandsParams, name: str, old: Any
    ) -> None:
        params_mod.param_changed(dataset, params, name, old)

    def apply_limits(self, params: BandsParams, axes_limits: AxesLimits) -> None:
        xlim, ylim = axes_limits[0]
        params.emin, params.emax = ylim
        params.xmin, params.xmax = xlim

    def legacy_params(self, params: BandsParams, folder: Path, memory: FolderMemory) -> None:
        """K-point labels typed before ``bands.plot`` existed."""
        if labels := memory.labels(folder):
            params.labels = ", ".join(labels)

    def default_labels(self, dataset: BandsDataset) -> list[str]:
        return list(dataset.labels)

    def load(self, result: DetectionResult, sniff: SniffFn) -> BandsDataset:
        return load_dataset(result, sniff)

    def render(
        self, figure: FigureBase, dataset: BandsDataset, params: BandsParams, style: PlotStyle
    ) -> RenderInfo:
        return render_mod.render_bands(figure, dataset, params, style)

    def table(self, dataset: BandsDataset, params: BandsParams) -> PlotTable:
        return table_mod.bands_table(dataset, params)

    def format_coordinates(
        self, x: float, y: float, axes_index: int, dataset: BandsDataset, params: BandsParams
    ) -> str:
        return render_mod.format_coordinates(x, y, axes_index, dataset, params)

    @staticmethod
    def tick_labels(dataset: BandsDataset, params: BandsParams) -> list[str]:
        return render_mod.tick_labels(dataset, params)

    @staticmethod
    def summary(dataset: BandsDataset) -> str:
        return render_mod.summary(dataset)
