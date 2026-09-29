"""Detect-only calculation types: structural relaxations and informational SCF/CALC tags."""

from __future__ import annotations

from typing import ClassVar

from ..sniff import FileKind, FileSniff
from .base import CalculationModule, FileRole, output_of


class RelaxModule(CalculationModule):
    kind: ClassVar[str] = "relax"
    badge: ClassVar[str] = "RELAX"
    display_name: ClassVar[str] = "Otimização estrutural"
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole(
            "relax_in",
            "Entrada relax/vc-relax (pw.x)",
            output_of(FileKind.PW_IN, "relax", "vc-relax"),
            ("relax*.in", "vc-relax*.in"),
            anchor=True,
        ),
        FileRole(
            "relax_out",
            "Saída relax/vc-relax (pw.x)",
            output_of(FileKind.PW_OUT, "relax", "vc-relax"),
            ("relax*.out", "vc-relax*.out"),
            required=True,
            anchor=True,
        ),
    )


class ScfModule(CalculationModule):
    kind: ClassVar[str] = "scf"
    badge: ClassVar[str] = "SCF"
    display_name: ClassVar[str] = "Cálculo SCF"
    fallback: ClassVar[bool] = True
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole(
            "scf_out",
            "Saída SCF (pw.x)",
            output_of(FileKind.PW_OUT, "scf"),
            ("scf*.out",),
            required=True,
            anchor=True,
        ),
    )


def _any_output(s: FileSniff) -> bool:
    return s.is_output


class CalcModule(CalculationModule):
    kind: ClassVar[str] = "calc"
    badge: ClassVar[str] = "CALC"
    display_name: ClassVar[str] = "Cálculo QE"
    fallback: ClassVar[bool] = True
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole("output", "Saída do Quantum ESPRESSO", _any_output, multiple=True, anchor=True),
    )
