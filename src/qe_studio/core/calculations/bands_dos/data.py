"""The bands + DOS dataset: the two datasets, loaded as each module loads its own."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...compounds import Compound, compound_of
from ...qe.structure import read_sites
from ..bands.data import BandsDataset
from ..base import DetectionResult, LoadError, SniffFn
from ..pdos.data import PdosDataset
from .pair import PARTS


@dataclass
class BandsDosDataset:
    folder: Path  # the bands folder
    bands: BandsDataset
    dos: PdosDataset
    bands_compound: Compound | None = None  # to tell a DOS of another compound (atom selection)
    warnings: list[str] = field(default_factory=list)


def load_dataset(result: DetectionResult, sniff: SniffFn) -> BandsDosDataset:
    """Both parts through their modules' ``load_cached``, one after the other in this worker: an
    open band or PDOS tab of the same files has them loaded already."""
    if len(result.parts) != len(PARTS):
        raise LoadError("Bandas com DOS precisa de uma pasta de bandas e uma de PDOS.")
    bands_result, dos_result = result.parts
    bands: BandsDataset = bands_result.module.load_cached(bands_result, sniff)
    dos: PdosDataset = dos_result.module.load_cached(dos_result, sniff)
    scf = bands_result.file("scf_out")
    warnings = [
        f"{label}: {warning}"
        for (_prefix, label), part in zip(PARTS, (bands, dos), strict=True)
        for warning in part.warnings
    ]
    compound = compound_of(read_sites(scf)) if scf is not None else None
    return BandsDosDataset(result.folder, bands, dos, compound, warnings)
