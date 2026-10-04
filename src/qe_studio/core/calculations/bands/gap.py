"""The energy gap of a band structure: what the footer and the legend both say (spec 20)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from matplotlib.lines import Line2D

from ...plotting.gap_label import gap_handle, gap_label

if TYPE_CHECKING:
    from .data import BandsDataset
    from .params import BandsParams


@dataclass(frozen=True)
class GapEntry:
    """One gap: ``channel`` is None (no spin), ``up`` / ``down`` or ``global`` (both channels)."""

    channel: str | None
    value: float


def gap_entries(dataset: BandsDataset) -> list[GapEntry]:
    """The gaps of the dataset; none for a metal.

    A spin run (or one whose ↓ channel is missing) has the gap of each channel that has one, and
    the global gap when both do; a run without spin has the one gap.
    """
    if dataset.edges:
        entries = [
            GapEntry(channel, edges.gap)
            for channel, edges in dataset.edges.items()
            if edges.gap is not None
        ]
        if dataset.gap is not None:
            entries.append(GapEntry("global", dataset.gap))
        return entries
    return [] if dataset.gap is None else [GapEntry(None, dataset.gap)]


def gap_handles(dataset: BandsDataset, params: BandsParams) -> list[Line2D]:
    """Legend entries of the gaps, when the parameter asks for them."""
    if not params.legend_gap:
        return []
    return [gap_handle(gap_label(e.value, e.channel)) for e in gap_entries(dataset)]
