"""Band data: the dataset, eigenvalue loading, k-path ticks and band edges (PRD §4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ...qe import bands_x
from ...qe.pw_input import parse_input
from ...qe.pw_output import PwOutput, read_structure
from ...sniff import sniff
from ..base import DetectionResult, LoadError

BOHR_TO_ANGSTROM = 0.529177210903
EDGE_TOL = 1e-3  # eV: a band within this of E_F is not counted as crossing it
CHANNELS = ("up", "down")
# Roles holding the eigenvalue file of each spin channel: (.gnu, filband).
CHANNEL_ROLES = {"up": ("gnu", "filband"), "down": ("gnu_down", "filband_down")}


@dataclass(frozen=True)
class ChannelEdges:
    """Band edges of one spin channel around its Fermi energy (``None`` = not determinable)."""

    fermi: float | None
    vbm: float | None = None
    cbm: float | None = None
    metallic: bool = False  # a band crosses E_F
    n_occupied: int | None = None  # filled bands, when the edges come from the electron count

    @property
    def gap(self) -> float | None:
        if self.vbm is None or self.cbm is None:
            return None
        return self.cbm - self.vbm


def valence_mask(energies: np.ndarray, fermi: float, tol: float = EDGE_TOL) -> np.ndarray:
    """Bands (rows of ``energies[band, k]``) lying entirely below ``fermi``."""
    return energies.max(axis=1) <= fermi + tol


def channel_edges(energies: np.ndarray, fermi: float | None, tol: float = EDGE_TOL) -> ChannelEdges:
    """VBM / CBM of one channel from its Fermi energy (``n_electrons / 2`` does not hold with spin).

    A band is valence when its top is at or below E_F, conduction when its bottom is at or above
    it, and crosses E_F otherwise: any crossing band makes the channel metallic, and so does a gap
    that closes (≤ ``tol``).
    """
    if fermi is None:
        return ChannelEdges(None)
    valence = valence_mask(energies, fermi, tol)
    conduction = ~valence & (energies.min(axis=1) >= fermi - tol)
    if (~valence & ~conduction).any():
        return ChannelEdges(fermi, metallic=True)
    vbm = float(energies[valence].max()) if valence.any() else None
    cbm = float(energies[conduction].min()) if conduction.any() else None
    if vbm is not None and cbm is not None and cbm - vbm <= tol:
        return ChannelEdges(fermi, metallic=True)
    return ChannelEdges(fermi, vbm, cbm)


def occupied_count(n_electrons: float | None, n_bands: int) -> int | None:
    """Bands an electron count fills completely, or None if it is fractional or fills none or all."""
    if n_electrons is None:
        return None
    n_occ = int(round(n_electrons))
    if abs(n_electrons - n_occ) > 1e-6 or not 0 < n_occ < n_bands:
        return None
    return n_occ


def count_edges(energies: np.ndarray, n_occ: int, fermi: float | None) -> ChannelEdges:
    """Edges of ``n_occ`` filled bands (fixed occupations): VBM at the top of band ``n_occ``, CBM at
    the bottom of the next one, metallic if they overlap (≤ ``EDGE_TOL``)."""
    vbm = float(energies[n_occ - 1].max())
    cbm = float(energies[n_occ].min())
    if cbm - vbm <= EDGE_TOL:
        return ChannelEdges(fermi, metallic=True, n_occupied=n_occ)
    return ChannelEdges(fermi, vbm, cbm, n_occupied=n_occ)


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
    # Spin (collinear, nspin = 2): ``bands`` is the ↑ channel and ``bands_down`` the ↓ one.
    bands_down: bands_x.BandData | None = None
    # Per channel, spin runs only (just "up" when the ↓ channel is missing).
    edges: dict[str, ChannelEdges] = field(default_factory=dict)
    fermi_up_down: tuple[float, float] | None = None  # fixed magnetization: one E_F per channel
    magnetization: float | None = None  # total, μB/cell

    @property
    def spin(self) -> bool:
        return self.bands_down is not None

    def band_data(self, channel: str) -> bands_x.BandData | None:
        return self.bands_down if channel == "down" else self.bands

    @property
    def gap(self) -> float | None:
        if self.vbm is None or self.cbm is None:
            return None
        return self.cbm - self.vbm

    def reference(self, mode: str) -> float:
        if mode == "vbm" and self.vbm is not None:
            return self.vbm
        if mode == "midgap" and self.vbm is not None and self.cbm is not None:
            return (self.vbm + self.cbm) / 2
        if mode == "absolute" or self.fermi is None:
            return 0.0
        return self.fermi


def read_bands_input(path: Path | None):
    if path is None:
        return None
    try:
        return parse_input(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_dataset(result: DetectionResult) -> BandsDataset:
    warnings = list(result.warnings)
    scf_path = result.file("scf_out")
    pw = sniff(scf_path).pw if scf_path else None
    if pw is None or pw.fermi is None:
        warnings.append("energia de Fermi não encontrada: energias absolutas")
    bands, bands_down, source = _eigenvalues(result, pw, warnings)
    ticks, labels, tick_source = _ticks(result, bands, source, warnings)
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
        bands_down=bands_down,
        fermi_up_down=pw.fermi_up_down if pw else None,
        magnetization=pw.total_magnetization if pw else None,
    )
    if pw is not None:
        _band_edges(dataset, pw)
        atoms = read_structure(read_text(scf_path)) if scf_path else None
        dataset.formula = atoms.get_chemical_formula() if atoms is not None else None
    return dataset


def _from_files(
    result: DetectionResult, channel: str, errors: list[str]
) -> tuple[bands_x.BandData, str] | None:
    """Eigenvalues of ``channel`` from its ``.gnu``, else its ``filband``; None if neither reads."""
    gnu_role, filband_role = CHANNEL_ROLES[channel]
    if (gnu := result.file(gnu_role)) is not None:
        try:
            return bands_x.read_gnu(read_text(gnu)), "gnu"
        except (OSError, bands_x.BandsFormatError) as exc:
            errors.append(f"{gnu.name}: {exc}")
    if (filband := result.file(filband_role)) is not None:
        try:
            return bands_x.read_filband(read_text(filband)).to_band_data(), "filband"
        except (OSError, bands_x.BandsFormatError) as exc:
            errors.append(f"{filband.name}: {exc}")
    return None


def _eigenvalues(
    result: DetectionResult, pw: PwOutput | None, warnings: list[str]
) -> tuple[bands_x.BandData, bands_x.BandData | None, str]:
    """``(↑ or only channel, ↓ channel or None, source)``."""
    errors: list[str] = []
    if (up := _from_files(result, "up", errors)) is not None:
        down = None
        if any(result.file(role) for role in CHANNEL_ROLES["down"]):
            down_errors: list[str] = []
            if (read := _from_files(result, "down", down_errors)) is not None:
                down = read[0]
            else:
                warnings.append(f"canal ↓ ilegível, gráfico só com ↑ ({'; '.join(down_errors)})")
        return up[0], down, up[1]
    if (bands_out := result.file("bands_out")) is not None:
        try:
            data, down = _bands_from_pw_output(bands_out, pw)
            warnings.append("autovalores lidos da saída do pw.x (bands.x não encontrado)")
            return data, down, "pw"
        except LoadError as exc:
            errors.append(str(exc))
    down_files = [p for p in map(result.file, CHANNEL_ROLES["down"]) if p is not None]
    if down_files:  # bands.x did run, for ↓ only: say so instead of "run bands.x"
        errors = [
            f"só o canal ↓ ({down_files[0].name}) foi encontrado: mapeie-o como ↑ ou rode o "
            "bands.x com spin_component = 1"
        ]
    raise LoadError("Não foi possível ler os autovalores:\n" + "\n".join(errors))


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
        warnings.append("caminho K_POINTS não corresponde aos dados: sem pontos de alta simetria")
    return [float(x[0]), float(x[-1])], ["", ""], "nenhum"


def _band_edges(dataset: BandsDataset, pw: PwOutput) -> None:
    if dataset.spin:
        spin_band_edges(dataset, pw)
        return
    if pw.spin_polarized:  # only the ↑ channel was found: its own edges, no global ones
        if pw.fermi is not None:
            dataset.edges = {"up": spin_channel_edges(dataset.bands.energies, 0, pw)}
        return
    if pw.n_electrons is None:
        return
    occupied = pw.n_electrons if pw.noncollinear else pw.n_electrons / 2
    n_occ = occupied_count(occupied, len(dataset.bands.energies))
    if n_occ is None:
        return
    edges = count_edges(dataset.bands.energies, n_occ, pw.fermi)
    if edges.gap is not None:
        dataset.n_occupied, dataset.vbm, dataset.cbm = n_occ, edges.vbm, edges.cbm


def spin_channel_edges(energies: np.ndarray, index: int, pw: PwOutput) -> ChannelEdges:
    """Edges of spin channel ``index`` (0 = ↑, 1 = ↓).

    With fixed occupations pw.x prints the HOMO / LUMO of both channels together, and a band path
    may top the HOMO of the SCF grid, so the bands are counted (``nelup`` / ``neldw``, printed with
    ``tot_magnetization``). With smearing, the channel's own E_F splits them.
    """
    if pw.fermi_kind in ("homo", "homo_lumo") and pw.n_electrons_up_down is not None:
        n_occ = occupied_count(pw.n_electrons_up_down[index], len(energies))
        if n_occ is not None:
            return count_edges(energies, n_occ, pw.fermi)
    fermi = pw.fermi_up_down[index] if pw.fermi_up_down else pw.fermi
    return channel_edges(energies, fermi)


def spin_band_edges(dataset: BandsDataset, pw: PwOutput) -> None:
    """Edges per channel (``spin_channel_edges``); the global ones only if both channels have a gap
    (so the "VBM" and "mid-gap" references and ``gap`` are the global VBM, CBM and gap)."""
    if pw.fermi is None or dataset.bands_down is None:
        return
    dataset.edges = {
        "up": spin_channel_edges(dataset.bands.energies, 0, pw),
        "down": spin_channel_edges(dataset.bands_down.energies, 1, pw),
    }
    up, down = dataset.edges["up"], dataset.edges["down"]
    if up.gap is None or down.gap is None:
        return
    vbm = max(v for v in (up.vbm, down.vbm) if v is not None)
    cbm = min(c for c in (up.cbm, down.cbm) if c is not None)
    if cbm - vbm > EDGE_TOL:
        dataset.vbm, dataset.cbm = vbm, cbm


def _bands_from_pw_output(
    path: Path, pw: PwOutput | None
) -> tuple[bands_x.BandData, bands_x.BandData | None]:
    """Last-resort eigenvalues from a pw.x bands run (only printed for < 100 k-points).

    With two spins (nspin = 2) both channels are read: ``(↑, ↓)``, else ``(bands, None)``.
    """
    atoms = read_structure(read_text(path))
    calc = atoms.calc if atoms is not None else None
    if atoms is None or calc is None or not calc.kpts:
        raise LoadError(f"{path.name}: pw.x não imprimiu os autovalores (rode o bands.x)")
    n_spins = calc.get_number_of_spins()
    if n_spins not in (1, 2):
        raise LoadError(f"{path.name}: número de spins não suportado ({n_spins})")
    kscaled = calc.get_ibz_k_points()
    kcart = kscaled @ atoms.cell.reciprocal()
    if pw is not None and pw.alat_bohr:
        kcart = kcart * pw.alat_bohr * BOHR_TO_ANGSTROM  # units of 2π/alat, as bands.x
    x = bands_x.path_coordinates(kcart)
    channels = [
        bands_x.BandData(
            x, np.array([calc.get_eigenvalues(kpt=k, spin=spin) for k in range(len(kscaled))]).T
        )
        for spin in range(n_spins)
    ]
    return channels[0], channels[1] if n_spins == 2 else None
