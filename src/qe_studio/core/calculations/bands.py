"""Electronic band structure (PRD §4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from ..plotting.draw import finish, new_axes
from ..plotting.style import PlotStyle
from ..qe import bands_x
from ..qe.pw_input import format_kpoint_label, parse_input
from ..qe.pw_output import PwOutput, read_structure
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

EIGEN_SOURCES = ("gnu", "filband", "bands_out")
BOHR_TO_ANGSTROM = 0.529177210903
REFERENCES = (
    ("fermi", "E_F (SCF)"),
    ("vbm", "Topo da valência (VBM)"),
    ("midgap", "Meio do gap"),
    ("absolute", "Absoluta"),
)
Y_LABELS = {
    "fermi": r"$E - E_F$ (eV)",
    "vbm": r"$E - E_{VBM}$ (eV)",
    "midgap": r"$E - E_{gap/2}$ (eV)",
    "absolute": r"$E$ (eV)",
}


@dataclass
class BandsDataset:
    folder: Path
    bands: bands_x.BandData
    source: str  # gnu | filband | pw
    fermi: float | None
    fermi_kind: str | None
    ticks: list[float]
    labels: list[str]  # raw labels from the input ("G", "Y2"…)
    tick_source: str
    n_occupied: int | None = None
    vbm: float | None = None
    cbm: float | None = None
    formula: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def gap(self) -> float | None:
        if self.vbm is None or self.cbm is None:
            return None
        return self.cbm - self.vbm

    def reference(self, mode: str) -> float:
        if mode == "vbm" and self.vbm is not None:
            return self.vbm
        if mode == "midgap" and self.gap is not None:
            return (self.vbm + self.cbm) / 2
        if mode == "absolute" or self.fermi is None:
            return 0.0
        return self.fermi


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


def read_bands_input(path: Path | None):
    if path is None:
        return None
    try:
        return parse_input(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


class BandsModule(CalculationModule):
    kind: ClassVar[str] = "bands"
    badge: ClassVar[str] = "BANDS"
    display_name: ClassVar[str] = "Estrutura de bandas"
    plottable: ClassVar[bool] = True
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
            "bandsx_out",
            "Saída do bands.x",
            output_of(FileKind.BANDSX_OUT),
            ("bands*.out",),
            anchor=True,
        ),
        FileRole("filband", "Dados de bandas (filband)", output_of(FileKind.FILBAND)),
        FileRole(
            "gnu",
            "Dados de bandas (.gnu)",
            output_of(FileKind.GNU_DATA),
            ("*.gnu", "*.dat.gnu"),
            anchor=True,
        ),
    )

    def select(
        self,
        role: FileRole,
        candidates: list[Path],
        sniffs: dict[Path, FileSniff],
        result: DetectionResult,
    ) -> list[Path]:
        if role.id in ("gnu", "filband"):
            preferred = self._named_by_bandsx(role.id, candidates, sniffs, result)
            if preferred:
                return [preferred]
        return super().select(role, candidates, sniffs, result)

    @staticmethod
    def _named_by_bandsx(
        role_id: str,
        candidates: list[Path],
        sniffs: dict[Path, FileSniff],
        result: DetectionResult,
    ) -> Path | None:
        names = []
        for path in candidates + list(sniffs):
            s = sniffs.get(path)
            if s and s.bandsx:
                names.append(s.bandsx.gnu_name if role_id == "gnu" else s.bandsx.filband_name)
        if role_id == "gnu":
            names += [f"{p.name}.gnu" for p in result.files.get("filband", [])]
        by_name = {p.name: p for p in candidates}
        for name in names:
            if name and Path(name).name in by_name:
                return by_name[Path(name).name]
        return None

    def finalize(
        self,
        result: DetectionResult,
        listing: FolderListing,
        sniffs: dict[Path, FileSniff],
        sniff: SniffFn,
    ) -> None:
        self.infer_from_neighbours(result, "scf_out", sniff)
        if not any(source in result.files for source in EIGEN_SOURCES):
            result.missing.append("gnu")
        if "bands_in" not in result.files:
            result.warnings.append("entrada de bandas não encontrada: pontos k sem rótulos")

        nks = None
        data_file = result.file("gnu") or result.file("filband")
        if data_file is not None:
            shape = (sniffs.get(data_file) or sniff(data_file)).shape
            nks = shape[1] if shape else None
        expected = None
        bands_out = result.file("bands_out")
        if bands_out is not None:
            pw = sniff(bands_out).pw
            expected = pw.n_kpoints if pw else None
        if expected is None:
            parsed = read_bands_input(result.file("bands_in"))
            if parsed and parsed.kpoints is not None and len(parsed.kpoints.weights):
                kp = parsed.kpoints
                expected = kp.path_length if kp.is_path else len(kp.weights)
        if nks is not None and expected is not None and nks != expected:
            result.warnings.append(
                f"os dados de bandas têm {nks} pontos k, mas o cálculo de bandas tem "
                f"{expected} (bands.x rodou sobre outra execução?)"
            )

    # -- plotting ------------------------------------------------------------------------------
    def default_params(self, config, dataset: BandsDataset) -> BandsParams:
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

    def param_schema(self, dataset: BandsDataset) -> list[ParamField]:
        references = [
            (value, label)
            for value, label in REFERENCES
            if value == "absolute"
            or (value == "fermi" and dataset.fermi is not None)
            or (value in ("vbm", "midgap") and dataset.gap is not None)
        ]
        return [
            ParamField("reference", "Referência", "Energia", "choice", choices=tuple(references)),
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
            *COMMON_FIELDS,
        ]

    def param_changed(self, dataset: BandsDataset, params: BandsParams, name: str, old) -> None:
        """Keep the visible absolute window when the energy reference changes."""
        if name == "reference":
            shift = dataset.reference(old) - dataset.reference(params.reference)
            params.emin += shift
            params.emax += shift

    def load(self, result: DetectionResult) -> BandsDataset:
        warnings = list(result.warnings)
        scf_path = result.file("scf_out")
        pw = sniff(scf_path).pw if scf_path else None
        if pw is None or pw.fermi is None:
            warnings.append("energia de Fermi não encontrada: energias absolutas")
        bands, source = self._eigenvalues(result, pw, warnings)
        ticks, labels, tick_source = self._ticks(result, bands, source, warnings)
        dataset = BandsDataset(
            folder=result.folder,
            bands=bands,
            source=source,
            fermi=pw.fermi if pw else None,
            fermi_kind=pw.fermi_kind if pw else None,
            ticks=ticks,
            labels=labels,
            tick_source=tick_source,
            warnings=list(dict.fromkeys(warnings)),
        )
        if pw is not None:
            self._band_edges(dataset, pw)
            atoms = read_structure(_read(scf_path)) if scf_path else None
            dataset.formula = atoms.get_chemical_formula() if atoms is not None else None
        return dataset

    @staticmethod
    def _eigenvalues(
        result: DetectionResult, pw: PwOutput | None, warnings: list[str]
    ) -> tuple[bands_x.BandData, str]:
        errors = []
        if (gnu := result.file("gnu")) is not None:
            try:
                return bands_x.read_gnu(_read(gnu)), "gnu"
            except (OSError, bands_x.BandsFormatError) as exc:
                errors.append(f"{gnu.name}: {exc}")
        if (filband := result.file("filband")) is not None:
            try:
                return bands_x.read_filband(_read(filband)).to_band_data(), "filband"
            except (OSError, bands_x.BandsFormatError) as exc:
                errors.append(f"{filband.name}: {exc}")
        if (bands_out := result.file("bands_out")) is not None:
            try:
                data = _bands_from_pw_output(bands_out, pw)
                warnings.append("autovalores lidos da saída do pw.x (bands.x não encontrado)")
                return data, "pw"
            except LoadError as exc:
                errors.append(str(exc))
        raise LoadError("Não foi possível ler os autovalores:\n" + "\n".join(errors))

    @staticmethod
    def _ticks(
        result: DetectionResult, bands: bands_x.BandData, source: str, warnings: list[str]
    ) -> tuple[list[float], list[str], str]:
        x = bands.x
        parsed = read_bands_input(result.file("bands_in"))
        kp = parsed.kpoints if parsed else None
        if kp is not None and kp.is_path and kp.path_length == bands.n_kpoints:
            return [float(x[i]) for i in kp.vertex_indices()], list(kp.labels), "entrada"
        bandsx_path = result.file("bandsx_out")
        hs = sniff(bandsx_path).bandsx if bandsx_path else None
        if hs and hs.hs_x and source != "pw":
            labels = list(kp.labels) if kp and len(kp.labels) == len(hs.hs_x) else []
            labels = labels or [""] * len(hs.hs_x)
            return list(hs.hs_x), labels, "bands.x"
        if kp is not None and kp.is_path:
            warnings.append(
                "caminho K_POINTS não corresponde aos dados: sem pontos de alta simetria"
            )
        return [float(x[0]), float(x[-1])], ["", ""], "nenhum"

    @staticmethod
    def _band_edges(dataset: BandsDataset, pw: PwOutput) -> None:
        if pw.n_electrons is None or pw.spin_polarized:
            return
        occupied = pw.n_electrons if pw.noncollinear else pw.n_electrons / 2
        n_occ = int(round(occupied))
        energies = dataset.bands.energies
        if abs(occupied - n_occ) > 1e-6 or not 0 < n_occ < len(energies):
            return
        vbm = float(energies[n_occ - 1].max())
        cbm = float(energies[n_occ].min())
        if cbm - vbm > 1e-3:
            dataset.n_occupied, dataset.vbm, dataset.cbm = n_occ, vbm, cbm

    def render(
        self, figure: Figure, dataset: BandsDataset, params: BandsParams, style: PlotStyle
    ) -> RenderInfo:
        ax = new_axes(figure, style)
        ref = dataset.reference(params.reference)
        x = dataset.bands.x
        energies = dataset.bands.energies - ref
        if dataset.n_occupied is not None:
            valence = np.arange(len(energies)) < dataset.n_occupied
        elif dataset.fermi is not None:
            valence = energies.max(axis=1) <= dataset.fermi - ref
        else:
            valence = np.zeros(len(energies), dtype=bool)
        handles = []
        for mask, color, label in (
            (valence, params.valence_color, "Valência"),
            (~valence, params.conduction_color, "Condução"),
        ):
            if mask.any():
                segments = [np.column_stack([x, e]) for e in energies[mask]]
                ax.add_collection(
                    LineCollection(segments, colors=color, linewidths=params.line_width)
                )
                handles.append(Line2D([], [], color=color, lw=params.line_width, label=label))

        ticks, labels = merged_ticks(dataset.ticks, self.tick_labels(dataset, params))
        if params.show_hs_lines:
            for tick in ticks[1:-1]:
                ax.axvline(tick, color=style.guide, lw=0.7, zorder=0)
        if dataset.fermi is not None and params.show_fermi_line:
            ax.axhline(
                dataset.fermi - ref,
                color=params.fermi_color,
                lw=0.9,
                ls=(0, (5, 3)),
                zorder=1,
            )
            handles.append(
                Line2D([], [], color=params.fermi_color, lw=0.9, ls=(0, (5, 3)), label="$E_F$")
            )
        ax.set_xticks(ticks, labels)
        xlim = (
            params.xmin if params.xmin is not None else float(x[0]),
            params.xmax if params.xmax is not None else float(x[-1]),
        )
        ax.set_xlim(*xlim)
        ax.set_ylim(params.emin, params.emax)
        ax.set_ylabel(Y_LABELS.get(params.reference, Y_LABELS["absolute"]))
        ax.yaxis.set_minor_locator(_auto_minor())
        ax.tick_params(axis="x", which="both", length=0, pad=6)
        ax.tick_params(axis="y", which="both", right=True)
        finish(figure, ax, params, handles)
        return RenderInfo(xlim, (params.emin, params.emax), self.summary(dataset))

    @staticmethod
    def tick_labels(dataset: BandsDataset, params: BandsParams) -> list[str]:
        raw = dataset.labels
        if params.labels.strip():
            typed = [part.strip() for part in params.labels.split(",")]
            raw = (typed + [""] * len(dataset.ticks))[: len(dataset.ticks)]
        return [format_kpoint_label(label) for label in raw]

    @staticmethod
    def summary(dataset: BandsDataset) -> str:
        parts = []
        if dataset.fermi is not None:
            name = "E_F" if dataset.fermi_kind in ("fermi", "spin_fermi") else "HOMO"
            parts.append(f"{name} = {dataset.fermi:.4f} eV")
        if dataset.gap is not None:
            parts.append(f"E_gap = {dataset.gap:.3f} eV")
        elif dataset.fermi is not None:
            parts.append("metálico")
        parts.append(f"{dataset.bands.n_bands} bandas × {dataset.bands.n_kpoints} pontos k")
        return " · ".join(parts)


def merged_ticks(ticks: list[float], labels: list[str]) -> tuple[list[float], list[str]]:
    """Merge coincident ticks (path discontinuities) into ``A|B`` labels."""
    out_ticks: list[float] = []
    out_labels: list[str] = []
    for tick, label in zip(ticks, labels, strict=False):
        if out_ticks and abs(tick - out_ticks[-1]) < 1e-4:
            if label and label != out_labels[-1]:
                out_labels[-1] = f"{out_labels[-1]}|{label}" if out_labels[-1] else label
            continue
        out_ticks.append(tick)
        out_labels.append(label)
    return out_ticks, out_labels


def _auto_minor():
    from matplotlib.ticker import AutoMinorLocator

    return AutoMinorLocator()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _bands_from_pw_output(path: Path, pw: PwOutput | None) -> bands_x.BandData:
    """Last-resort eigenvalues from a pw.x bands run (only printed for < 100 k-points)."""
    atoms = read_structure(_read(path))
    calc = atoms.calc if atoms is not None else None
    if calc is None or not calc.kpts:
        raise LoadError(f"{path.name}: pw.x não imprimiu os autovalores (rode o bands.x)")
    if calc.get_number_of_spins() != 1:
        raise LoadError(f"{path.name}: bandas com spin exigem o bands.x")
    kscaled = calc.get_ibz_k_points()
    energies = np.array([calc.get_eigenvalues(kpt=k) for k in range(len(kscaled))]).T
    kcart = kscaled @ atoms.cell.reciprocal()
    if pw is not None and pw.alat_bohr:
        kcart = kcart * pw.alat_bohr * BOHR_TO_ANGSTROM  # units of 2π/alat, as bands.x
    return bands_x.BandData(bands_x.path_coordinates(kcart), energies)
