"""Which two folders make a bands + DOS figure (spec 22), and the result that plots them together.

Decided from detection results only (the cache in the GUI, a fresh detection in the load worker),
so the context menu never reads a file and the UI never asks a module's kind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..bands import BandsModule
from ..base import CalculationModule, DetectionResult
from ..pdos import PdosModule

# Prefix of each part's roles in the combined result (``bands.gnu``, ``dos.pdos_atm``) and the label
# its files and warnings carry, in the order of ``DetectionResult.parts``.
PARTS = (("bands", "Bandas"), ("dos", "DOS"))

Results = Sequence[DetectionResult] | None


@dataclass(frozen=True)
class BandsDosPair:
    bands: DetectionResult
    dos: DetectionResult


def _plottable(results: Results, module_type: type) -> DetectionResult | None:
    return next(
        (r for r in results or () if isinstance(r.module, module_type) and r.plottable), None
    )


def ordered_pair(bands_results: Results, dos_results: Results) -> BandsDosPair | None:
    """The bands of the first folder and the PDOS of the second, both complete, or None."""
    bands = _plottable(bands_results, BandsModule)
    dos = _plottable(dos_results, PdosModule)
    return BandsDosPair(bands, dos) if bands is not None and dos is not None else None


def bands_dos_pair(a: Results, b: Results) -> BandsDosPair | None:
    """The pair two folders make, in either order; None when they make none, or two (each folder
    has both bands and a PDOS: which one is the DOS is anybody's guess). ``None`` results (folder
    not detected yet) make no pair."""
    found = [pair for pair in (ordered_pair(a, b), ordered_pair(b, a)) if pair is not None]
    return found[0] if len(found) == 1 else None


def pair_result(pair: BandsDosPair, module: CalculationModule[Any, Any]) -> DetectionResult:
    """The result ``module`` (the bands + DOS one) plots: the bands folder's, with both results as
    its ``parts`` and their files under prefixed roles (the panel's "Arquivos", the load cache)."""
    result = DetectionResult(module, pair.bands.folder, parts=(pair.bands, pair.dos))
    for (prefix, label), part in zip(PARTS, result.parts, strict=True):
        result.files.update({f"{prefix}.{role}": paths for role, paths in part.files.items()})
        result.methods.update({f"{prefix}.{role}": m for role, m in part.methods.items()})
        result.warnings += [f"{label}: {warning}" for warning in part.warnings]
    return result
