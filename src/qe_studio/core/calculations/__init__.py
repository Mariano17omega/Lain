"""Registry of calculation modules. Add new calculation types here (NFR §7)."""

from .bands import BandsModule
from .base import CalculationModule, DetectionResult, FileRole, FolderListing, Method
from .info import CalcModule, RelaxModule, ScfModule
from .pdos import PdosModule

REGISTRY: tuple[CalculationModule, ...] = (
    BandsModule(),
    PdosModule(),
    RelaxModule(),
    ScfModule(),
    CalcModule(),
)


def module_for(kind: str) -> CalculationModule:
    return next(m for m in REGISTRY if m.kind == kind)


__all__ = [
    "REGISTRY",
    "CalculationModule",
    "DetectionResult",
    "FileRole",
    "FolderListing",
    "Method",
    "module_for",
]
