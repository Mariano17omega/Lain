"""Registry of calculation modules. Add new calculation types here (NFR §7)."""

from typing import Any

from ..sniff import FileSniff
from .bands import BandsModule
from .bands_dos import BandsDosModule
from .base import CalculationModule, DetectionResult, FileRole, FolderListing, Method
from .info import CalcModule
from .pdos import PdosModule
from .relax import RelaxModule
from .scf import ScfModule

REGISTRY: tuple[CalculationModule[Any, Any], ...] = (
    BandsModule(),
    PdosModule(),
    RelaxModule(),
    ScfModule(),
    CalcModule(),
    BandsDosModule(),  # never detected: made from two folders (spec 22)
)


def module_for(kind: str) -> CalculationModule[Any, Any]:
    return next(m for m in REGISTRY if m.kind == kind)


def module_for_file(
    sniff: FileSniff | None, modules: tuple[CalculationModule[Any, Any], ...] = REGISTRY
) -> CalculationModule[Any, Any] | None:
    """The plottable module that can plot this one file alone (its ``single_file_role``), if any."""
    if sniff is None:
        return None
    return next(
        (
            m
            for m in modules
            if m.plottable and m.single_file_role and m.role(m.single_file_role).accepts(sniff)
        ),
        None,
    )


def describe_plottable(modules: tuple[CalculationModule[Any, Any], ...] = REGISTRY) -> str:
    """Names of the calculations one can map by hand, for a sentence: "a, b ou c" (lowercase)."""
    names = [m.display_name.lower() for m in modules if m.plottable and m.selectable]
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
    "module_for_file",
]
