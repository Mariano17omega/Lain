"""Bands + DOS in one figure with a shared energy axis (spec 22), split like ``bands`` and ``pdos``.

``pair`` decides which two folders make the figure, ``data`` loads both datasets, ``params`` maps the
parameters onto each panel's, ``render`` draws with the band and PDOS drawing functions.
"""

from .data import BandsDosDataset
from .module import BandsDosModule
from .pair import BandsDosPair, bands_dos_pair, ordered_pair, pair_result
from .params import BandsDosParams

__all__ = [
    "BandsDosDataset",
    "BandsDosModule",
    "BandsDosPair",
    "BandsDosParams",
    "bands_dos_pair",
    "ordered_pair",
    "pair_result",
]
