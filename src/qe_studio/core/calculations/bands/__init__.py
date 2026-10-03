"""Electronic band structure (PRD §4.2), split by responsibility.

``module`` ties the parts together; ``detection`` pairs bands.x products and checks them, ``data``
loads eigenvalues and band edges, ``params`` holds the plot parameters and schema, ``render`` draws.
"""

from .data import BandsDataset, read_bands_input
from .module import BandsModule
from .params import BandsParams
from .render import merged_ticks

__all__ = ["BandsDataset", "BandsModule", "BandsParams", "merged_ticks", "read_bands_input"]
