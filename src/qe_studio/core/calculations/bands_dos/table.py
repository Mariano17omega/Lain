"""The bands + DOS figure as columns (spec 32 R4): the two blocks, side by side."""

from __future__ import annotations

from ...plotting.table import PlotTable
from ..bands.params import ENERGY_NAMES
from ..bands.table import bands_table
from ..pdos.table import pdos_table
from .data import BandsDosDataset
from .params import BandsDosParams, bands_view, dos_view


def bands_dos_table(dataset: BandsDosDataset, params: BandsDosParams) -> PlotTable:
    """The bands (``k`` and the bands) then the PDOS (its energy and the curves), the energies of
    both measured from the bands' reference, as ``render_bands_dos`` draws them. The blocks have
    their own x and may differ in length (the shorter one is blank at its end)."""
    bands, dos = dataset.bands, dataset.dos
    name = ENERGY_NAMES.get(params.reference, ENERGY_NAMES["absolute"])
    return bands_table(bands, bands_view(params)) + pdos_table(
        dos, dos_view(params), ref=bands.reference(params.reference), energy_name=name
    )
