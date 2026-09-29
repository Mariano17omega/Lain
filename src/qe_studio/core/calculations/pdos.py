"""Projected density of states (PRD §4.3)."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import numpy as np
from matplotlib.colors import to_hex, to_rgb
from matplotlib.figure import Figure

from ...config import DEFAULT_ORBITAL_COLORS
from ..plotting.draw import finish, new_axes
from ..plotting.style import PlotStyle
from ..qe import projwfc
from ..sniff import FileKind, FileSniff, sniff
from .base import (
    CalculationModule,
    DetectionResult,
    FileRole,
    FolderListing,
    LoadError,
    SniffFn,
    output_of,
)
from .params import COMMON_FIELDS, CommonParams, ParamField, RenderInfo, apply_common_config

GROUPINGS = (
    ("species_orbital", "Espécie + orbital"),
    ("species", "Espécie"),
    ("orbital", "Orbital"),
)
ORIENTATIONS = (("horizontal", "Energia no eixo x"), ("vertical", "Energia no eixo y"))


@dataclass
class PdosDataset:
    folder: Path
    data: projwfc.PdosData
    fermi_scf: float | None
    fermi_nscf: float | None
    warnings: list[str] = field(default_factory=list)

    def fermi(self, source: str) -> float | None:
        if source == "nscf" and self.fermi_nscf is not None:
            return self.fermi_nscf
        return self.fermi_scf if self.fermi_scf is not None else self.fermi_nscf


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
    total_color: str = ""  # empty = theme text color
    fill_occupied: bool = True
    show_fermi_line: bool = True
    fermi_color: str = "#f43f5e"
    hidden_series: list[str] = field(default_factory=list)
    series_colors: dict[str, str] = field(default_factory=dict)
    orbital_colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ORBITAL_COLORS))
    show_legend: bool = True


def series_label(key: tuple[str, str]) -> str:
    species, orbital = key
    return " ".join(part for part in (species, orbital) if part)


def _shade(color: str, index: int) -> str:
    """Distinguish species sharing an orbital color by stepping lightness."""
    if index == 0:
        return color
    h, lightness, s = colorsys.rgb_to_hls(*to_rgb(color))
    step = 0.14 * ((index + 1) // 2) * (1 if index % 2 else -1)
    return to_hex(colorsys.hls_to_rgb(h, min(max(lightness + step, 0.15), 0.85), s))


def _group_key(path: Path) -> tuple[Path, str]:
    meta = projwfc.parse_atm_name(path.name)
    return path.parent, meta.prefix if meta else ""


def _newest(paths: list[Path]) -> float:
    try:
        return max(p.stat().st_mtime for p in paths)
    except OSError:
        return 0.0


class PdosModule(CalculationModule):
    kind: ClassVar[str] = "pdos"
    badge: ClassVar[str] = "PDOS"
    display_name: ClassVar[str] = "Densidade de estados projetada"
    plottable: ClassVar[bool] = True
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
    def default_params(self, config, dataset: PdosDataset) -> PdosParams:
        plot = config.plot
        params = PdosParams(
            shift_to_fermi=plot.shift_to_fermi and dataset.fermi("scf") is not None,
            emin=plot.energy_min,
            emax=plot.energy_max,
            fermi_color=plot.fermi_color,
            orbital_colors=dict(plot.orbital_colors),
        )
        params.fermi_source = "scf" if dataset.fermi_scf is not None else "nscf"
        if not params.shift_to_fermi and (fermi := dataset.fermi(params.fermi_source)) is not None:
            params.emin += fermi
            params.emax += fermi
        apply_common_config(params, config)
        params.show_legend = True
        return params

    def param_schema(self, dataset: PdosDataset) -> list[ParamField]:
        sources = [("scf", "SCF")] if dataset.fermi_scf is not None else []
        if dataset.fermi_nscf is not None:
            sources.append(("nscf", "NSCF"))
        return [
            ParamField("fermi_source", "E_F de", "Energia", "choice", choices=tuple(sources)),
            ParamField("shift_to_fermi", "Referenciar a E_F", "Energia", "bool"),
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
            ParamField("orientation", "Orientação", "Eixo X", "choice", choices=ORIENTATIONS),
            ParamField(
                "dos_max",
                "DOS máx",
                "Eixo X",
                "float",
                minimum=0,
                maximum=1e6,
                step=0.5,
                decimals=2,
                suffix="est./eV",
                optional=True,
            ),
            ParamField("grouping", "Agrupar por", "Projeções", "choice", choices=GROUPINGS),
            ParamField("show_total", "DOS total", "Projeções", "bool"),
            ParamField("fill_occupied", "Preencher estados ocupados", "Projeções", "bool"),
            ParamField("hidden_series", "Séries", "Projeções", "series"),
            ParamField("fermi_color", "Fermi", "Estilo", "color"),
            *COMMON_FIELDS,
        ]

    def param_changed(self, dataset: PdosDataset, params: PdosParams, name: str, old) -> None:
        """Keep the visible absolute window when the energy reference changes."""
        if name in ("shift_to_fermi", "fermi_source"):
            before = self._reference(dataset, params, **{name: old})
            after = self._reference(dataset, params)
            params.emin += before - after
            params.emax += before - after

    @staticmethod
    def _reference(dataset: PdosDataset, params: PdosParams, **override) -> float:
        shift = override.get("shift_to_fermi", params.shift_to_fermi)
        source = override.get("fermi_source", params.fermi_source)
        fermi = dataset.fermi(source)
        return fermi if shift and fermi is not None else 0.0

    def load(self, result: DetectionResult) -> PdosDataset:
        tot = result.file("pdos_tot")
        try:
            data = projwfc.load_pdos(result.files.get("pdos_atm", []), tot)
        except (OSError, ValueError) as exc:
            raise LoadError(f"Não foi possível ler a PDOS: {exc}") from exc

        def fermi_of(role: str) -> float | None:
            path = result.file(role)
            pw = sniff(path).pw if path else None
            return pw.fermi if pw else None

        dataset = PdosDataset(
            result.folder,
            data,
            fermi_of("scf_out"),
            fermi_of("nscf_out"),
            list(dict.fromkeys([*result.warnings, *data.warnings])),
        )
        if dataset.fermi("scf") is None:
            dataset.warnings.append("energia de Fermi não encontrada: energias absolutas")
        return dataset

    def series_colors(
        self, dataset: PdosDataset, params: PdosParams, style: PlotStyle
    ) -> dict[str, str]:
        """Color of every group for the current grouping (user overrides first)."""
        orbital_colors = {**DEFAULT_ORBITAL_COLORS, **params.orbital_colors}
        species_index = {name: i for i, name in enumerate(dataset.data.species)}
        colors = {}
        for i, key in enumerate(projwfc.aggregate(dataset.data, params.grouping)):
            label = series_label(key)
            species, orbital = key
            if orbital:
                color = _shade(orbital_colors[orbital], species_index.get(species, 0))
            else:
                color = style.palette[i % len(style.palette)]
            colors[label] = params.series_colors.get(label, color)
        return colors

    def render(
        self, figure: Figure, dataset: PdosDataset, params: PdosParams, style: PlotStyle
    ) -> RenderInfo:
        ax = new_axes(figure, style)
        data = dataset.data
        fermi = dataset.fermi(params.fermi_source)
        ref = fermi if params.shift_to_fermi and fermi is not None else 0.0
        energy = data.energy - ref
        fermi_rel = None if fermi is None else fermi - ref
        window = (energy >= params.emin) & (energy <= params.emax)
        vertical = params.orientation == "vertical"
        spin = data.spin_polarized
        peak = 0.0

        def draw(values: np.ndarray, color: str, label: str | None, width: float, alpha: float):
            nonlocal peak
            if window.any():
                peak = max(peak, float(np.abs(values[window]).max()))
            if vertical:
                ax.plot(values, energy, color=color, lw=width, label=label)
            else:
                ax.plot(energy, values, color=color, lw=width, label=label)
            if params.fill_occupied and fermi_rel is not None:
                occupied = energy <= fermi_rel
                fill = ax.fill_betweenx if vertical else ax.fill_between
                fill(energy, 0, values, where=occupied, color=color, alpha=alpha, lw=0)

        def channel(ch: projwfc.Channel, color: str, label: str, width: float, alpha: float):
            draw(ch.up, color, label, width, alpha)
            if spin and ch.down is not None:
                draw(-ch.down, color, None, width, alpha)

        if params.show_total and data.total is not None:
            label = "Total (Σ PDOS)" if data.total_is_sum else "Total"
            color = params.total_color or style.total_dos
            channel(data.total, color, label, params.line_width, 0.12)
        colors = self.series_colors(dataset, params, style)
        for key, ch in projwfc.aggregate(data, params.grouping).items():
            label = series_label(key)
            if label not in params.hidden_series:
                channel(ch, colors[label], label, params.line_width, 0.22)

        top = params.dos_max if params.dos_max else (peak * 1.08 or 1.0)
        dos_lim = (-top if spin else 0.0, top)
        e_lim = (params.emin, params.emax)
        e_label = r"$E - E_F$ (eV)" if ref else r"$E$ (eV)"
        dos_label = "PDOS (estados/eV)"
        guide = {"color": style.guide, "lw": 0.7, "zorder": 0}
        fermi_line = {"color": params.fermi_color, "lw": 0.9, "ls": (0, (5, 3))}
        if vertical:
            ax.set_xlim(*dos_lim)
            ax.set_ylim(*e_lim)
            ax.set_xlabel(dos_label)
            ax.set_ylabel(e_label)
            if spin:
                ax.axvline(0, **guide)
            if params.show_fermi_line and fermi_rel is not None:
                ax.axhline(fermi_rel, **fermi_line)
        else:
            ax.set_xlim(*e_lim)
            ax.set_ylim(*dos_lim)
            ax.set_xlabel(e_label)
            ax.set_ylabel(dos_label)
            if spin:
                ax.axhline(0, **guide)
            if params.show_fermi_line and fermi_rel is not None:
                ax.axvline(fermi_rel, **fermi_line)
        ax.minorticks_on()
        ax.tick_params(which="both", top=True, right=True)
        finish(figure, ax, params)
        xlim, ylim = (dos_lim, e_lim) if vertical else (e_lim, dos_lim)
        return RenderInfo(xlim, ylim, self.summary(dataset, params))

    @staticmethod
    def summary(dataset: PdosDataset, params: PdosParams) -> str:
        parts = []
        fermi = dataset.fermi(params.fermi_source)
        if fermi is not None:
            parts.append(f"E_F = {fermi:.4f} eV ({params.fermi_source.upper()})")
        data = dataset.data
        parts.append(f"{len(data.series)} projeções · {len(data.species)} espécies")
        if data.spin_polarized:
            parts.append("spin polarizado")
        return " · ".join(parts)
