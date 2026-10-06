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


NO_GAP_NOTE = "Sem gap para a legenda: sistema metálico ao longo do caminho"
NO_COUNT_NOTE = "Sem gap para a legenda: sem a saída do SCF não há contagem de elétrons"


def legend_gap_notes(dataset: BandsDataset, params: BandsParams) -> tuple[str, ...]:
    """Why a gap asked for in a visible legend is not there (the readout's ⚠ lines, never the
    figure); empty when it is there or ``dataset.gap_note`` already says why."""
    if not (params.legend_gap and params.show_legend) or dataset.gap_note or gap_entries(dataset):
        return ()
    return (NO_GAP_NOTE if dataset.fermi is not None else NO_COUNT_NOTE,)


def gap_handles(dataset: BandsDataset, params: BandsParams) -> list[Line2D]:
    """Legend entries of the gaps, when the parameter asks for them."""
    if not params.legend_gap:
        return []
    return [gap_handle(gap_label(e.value, e.channel)) for e in gap_entries(dataset)]
