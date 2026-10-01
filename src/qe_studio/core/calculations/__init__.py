"""Registry of calculation modules. Add new calculation types here (NFR §7)."""

from typing import Any

from .bands import BandsModule
from .base import CalculationModule, DetectionResult, FileRole, FolderListing, Method
from .info import CalcModule, ScfModule
from .pdos import PdosModule
from .relax import RelaxModule

REGISTRY: tuple[CalculationModule[Any, Any], ...] = (
    BandsModule(),
    PdosModule(),
    RelaxModule(),
    ScfModule(),
    CalcModule(),
)


def module_for(kind: str) -> CalculationModule[Any, Any]:
    return next(m for m in REGISTRY if m.kind == kind)


def describe_plottable(modules: tuple[CalculationModule[Any, Any], ...] = REGISTRY) -> str:
    """Names of the plottable calculations for a sentence: "a, b ou c" (lowercase)."""
    names = [m.display_name.lower() for m in modules if m.plottable]
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} ou {names[-1]}"


__all__ = [
    "REGISTRY",
    "CalculationModule",
    "DetectionResult",
    "FileRole",
    "FolderListing",
    "Method",
    "describe_plottable",
    "module_for",
]
