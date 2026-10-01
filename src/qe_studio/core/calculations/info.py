"""Detect-only calculation types: informational SCF/CALC tags (no plot of their own)."""

from __future__ import annotations

from typing import ClassVar

from ..sniff import FileKind, FileSniff
from .base import CalculationModule, FileRole, output_of
from .params import CommonParams


class ScfModule(CalculationModule[None, CommonParams]):
    kind: ClassVar[str] = "scf"
    badge: ClassVar[str] = "SCF"
    badge_token: ClassVar[str | None] = "scf"
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


class CalcModule(CalculationModule[None, CommonParams]):
    kind: ClassVar[str] = "calc"
    badge: ClassVar[str] = "CALC"
    badge_token: ClassVar[str | None] = "calc"
    display_name: ClassVar[str] = "Cálculo QE"
    fallback: ClassVar[bool] = True
    roles: ClassVar[tuple[FileRole, ...]] = (
        FileRole("output", "Saída do Quantum ESPRESSO", _any_output, multiple=True, anchor=True),
    )
