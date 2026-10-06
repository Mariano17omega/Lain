"""The bands of a band structure plot as columns (spec 32 R4): what ``render`` draws, whole."""

from __future__ import annotations

import numpy as np

from ...plotting.table import Column, PlotTable
from .data import BandsDataset
from .params import ENERGY_NAMES, BandsParams
from .render import SYMBOL, shown_channels

K_UNIT = "2π/alat"  # the x of bands.x (``BandData.x``)


def bands_table(dataset: BandsDataset, params: BandsParams) -> PlotTable:
    """``k`` then one column per band, its energy minus the plot's reference (``E−E_F, eV``).
    A spin run adds ↑ / ↓ to the names, and only for the channels shown; the ↓ bands get a ``k`` of
    their own only if their path differs from the ↑ one."""
    ref = dataset.reference(params.reference)
    unit = f"{ENERGY_NAMES.get(params.reference, ENERGY_NAMES['absolute']).replace(' ', '')}, eV"
    columns: list[Column] = []
    first_x: np.ndarray | None = None
    for channel in shown_channels(dataset, params):
        band = dataset.band_data(channel)
        assert band is not None
        mark = f" {SYMBOL[channel]}" if dataset.spin else ""
        if first_x is None:
            first_x = band.x
            columns.append(Column(f"k ({K_UNIT})", band.x))
        elif not np.array_equal(band.x, first_x):
            columns.append(Column(f"k{mark} ({K_UNIT})", band.x))
        energies = band.energies - ref
        columns += [
            Column(f"Banda {number}{mark} ({unit})", energy)
            for number, energy in enumerate(energies, start=1)
        ]
    return PlotTable.of(columns)
