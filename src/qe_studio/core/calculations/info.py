"""Detect-only calculation types: the informational CALC tag (no plot of its own)."""

from __future__ import annotations

from typing import ClassVar

from ..sniff import FileSniff
from .base import CalculationModule, FileRole
from .params import CommonParams


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
