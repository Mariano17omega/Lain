"""Electronic band structure (PRD §4.2)."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ..qe.pw_input import parse_input
from ..sniff import FileKind, FileSniff
from .base import (
    CalculationModule,
    DetectionResult,
    FileRole,
    FolderListing,
    SniffFn,
    output_of,
)

EIGEN_SOURCES = ("gnu", "filband", "bands_out")


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
