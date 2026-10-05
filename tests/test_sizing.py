"""``nbytes_of`` (spec 27-4 R2.1): the array bytes an object keeps alive."""

from dataclasses import dataclass, field

import numpy as np

from qe_studio.core.calculations.bands.data import BandsDataset
from qe_studio.core.calculations.bands_dos.data import BandsDosDataset
from qe_studio.core.calculations.pdos.data import PdosDataset
from qe_studio.core.qe.bands_x import BandData
from qe_studio.core.qe.projwfc import Channel, PdosData, PdosSeries
from qe_studio.core.sizing import nbytes_of


def test_nothing_and_scalars_count_zero():
    assert nbytes_of(None) == 0
    assert nbytes_of(3.0) == nbytes_of("text") == nbytes_of(b"bytes") == 0


def test_band_data_is_the_sum_of_its_arrays():
    data = BandData(np.zeros(91), np.zeros((16, 91)))
    assert nbytes_of(data) == 91 * 8 + 16 * 91 * 8


def pdos_data(spin: bool) -> PdosData:
    energy = np.zeros(200)
    series = tuple(
        PdosSeries(
            atom, "Al", "3S", 0, None, Channel(np.zeros(200), np.zeros(200) if spin else None)
        )
        for atom in (1, 2, 3)
    )
    total = Channel(np.zeros(200), np.zeros(200) if spin else None)
    return PdosData(energy, series, total, False, ())


def test_pdos_data_counts_every_series_and_both_spin_channels():
    channels = 2
    assert nbytes_of(pdos_data(True)) == (200 + 4 * channels * 200) * 8
    assert nbytes_of(pdos_data(False)) == (200 + 4 * 200) * 8


def test_a_dataset_of_datasets_counts_both_halves():
    bands = BandsDataset.__new__(BandsDataset)  # only the arrays matter here
    bands.__dict__.update(bands=BandData(np.zeros(10), np.zeros((4, 10))), bands_down=None)
    dos = PdosDataset.__new__(PdosDataset)
    dos.__dict__.update(data=pdos_data(False))
    pair = BandsDosDataset.__new__(BandsDosDataset)
    pair.__dict__.update(bands=bands, dos=dos)
    assert nbytes_of(pair) == nbytes_of(bands) + nbytes_of(dos) > 0


def test_a_view_counts_its_base_once():
    base = np.zeros((100, 100))
    first, second = base[:, :3], base[:, 3:]  # two views of the same 80 kB table
    holder = BandData(first, second)
    assert nbytes_of(holder) == base.nbytes


def test_shared_arrays_count_once():
    shared = np.zeros(1000)
    assert nbytes_of([shared, (shared,), {"k": shared}]) == shared.nbytes


def test_cycles_end():
    @dataclass
    class Node:
        array: np.ndarray
        other: "Node | None" = field(default=None)

    a = Node(np.zeros(10))
    b = Node(np.zeros(20), a)
    a.other = b
    assert nbytes_of(a) == 30 * 8


def test_depth_is_limited():
    nested: list = [np.zeros(10)]
    for _ in range(20):
        nested = [nested]
    assert nbytes_of(nested) == 0  # too deep to be a dataset: not followed forever
