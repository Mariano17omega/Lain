"""Projected density of states (PRD §4.3)."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ..qe import projwfc
from ..sniff import FileKind, FileSniff
from .base import (
    CalculationModule,
    DetectionResult,
    FileRole,
    FolderListing,
    SniffFn,
    output_of,
)


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
