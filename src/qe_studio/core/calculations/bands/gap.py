"""The energy gap of a band structure: what the footer and the legend both say (spec 20), found by
the method the user picked (spec 34)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.lines import Line2D

from ....i18n import _
from ...plotting.gap_label import gap_handle, gap_label
from ..params import gap_method_in_force
from .data import EDGE_TOL

if TYPE_CHECKING:
    from .data import BandsDataset
    from .params import BandsParams

# The narrowest empty interval the "janela" method takes for a gap (the PDOS script's width): a
# dense metal has tiny spacings between its levels everywhere, which are no gap.
WINDOW_GAP_MIN_EV = 0.05


@dataclass(frozen=True)
class GapEntry:
    """One gap: ``channel`` is None (no spin), ``up`` / ``down`` or ``global`` (both channels)."""

    channel: str | None
    value: float


def gap_entries(dataset: BandsDataset, params: BandsParams | None = None) -> list[GapEntry]:
    """The gaps of the dataset by the method in force (``params`` None: ``auto``); none for a metal.

    ``auto``: a spin run (or one whose ↓ channel is missing) has the gap of each channel that has
    one, and the global gap when both do; a run without spin has the one gap. ``homo_lumo``: the one
    pair pw.x printed, for both channels. ``janela``: ``window_entries``.
    """
    method = "auto" if params is None else gap_method_in_force(params)
    if method == "homo_lumo":
        value = printed_gap(dataset.homo_lumo)
        return [] if value is None else [GapEntry(None, value)]
    if method == "janela" and params is not None:
        return window_entries(dataset, params)
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


def printed_gap(pair: tuple[float, float] | None) -> float | None:
    """LUMO − HOMO of a printed pair, or None without one or when it does not open (a metal)."""
    if pair is None:
        return None
    homo, lumo = pair
    return lumo - homo if lumo - homo > EDGE_TOL else None


def window_gap(
    energies: np.ndarray, ref: float, emin: float, emax: float
) -> tuple[float, float] | None:
    """The widest empty interval among the energies ``E − ref`` (every band, every k) inside the
    window ``(emin, emax)``: its two neighbours (top below, bottom above, relative to ``ref``), or
    None when no spacing reaches ``WINDOW_GAP_MIN_EV``. Depends on the window, as it is meant to."""
    low, high = sorted((emin, emax))
    values = np.ravel(energies) - ref
    inside = np.sort(values[(values > low) & (values < high)])
    if len(inside) < 2:
        return None
    steps = np.diff(inside)
    index = int(np.argmax(steps))
    if steps[index] < WINDOW_GAP_MIN_EV:
        return None
    return float(inside[index]), float(inside[index + 1])


def window_entries(dataset: BandsDataset, params: BandsParams) -> list[GapEntry]:
    """The ``janela`` gaps, in the plot's reference and energy window. A spin run has one per
    channel and the global one when both have one (``spin_band_edges``'s rule)."""
    ref = dataset.reference(params.reference)

    def edges(energies: np.ndarray) -> tuple[float, float] | None:
        return window_gap(energies, ref, params.emin, params.emax)

    if not dataset.spin:
        found = edges(dataset.bands.energies)
        channel = "up" if dataset.edges else None  # a spin run with the ↑ channel only
        return [] if found is None else [GapEntry(channel, found[1] - found[0])]
    assert dataset.bands_down is not None
    by_channel = {
        "up": edges(dataset.bands.energies),
        "down": edges(dataset.bands_down.energies),
    }
    entries = [GapEntry(ch, e[1] - e[0]) for ch, e in by_channel.items() if e is not None]
    up, down = by_channel["up"], by_channel["down"]
    if up is not None and down is not None:
        vbm, cbm = max(up[0], down[0]), min(up[1], down[1])
        if cbm - vbm > EDGE_TOL:
            entries.append(GapEntry("global", cbm - vbm))
    return entries


NO_GAP_NOTE = _("Sem gap para a legenda: sistema metálico ao longo do caminho")
NO_COUNT_NOTE = _("Sem gap para a legenda: sem a saída do SCF não há contagem de elétrons")
NO_HOMO_LUMO_NOTE = _(
    "Sem gap para a legenda: HOMO/LUMO não impresso pelo pw.x (só com ocupações fixas e nbnd "
    "maior que as bandas ocupadas)"
)
CLOSED_HOMO_LUMO_NOTE = _("Sem gap para a legenda: HOMO e LUMO impressos pelo pw.x coincidem")
NO_WINDOW_GAP_NOTE = _(
    "Sem gap para a legenda: nenhum intervalo vazio de pelo menos 0.05 eV na janela de energia"
)


def method_note(method: str, homo_lumo: tuple[float, float] | None) -> tuple[str, ...]:
    """Why ``homo_lumo`` or ``janela`` found no gap (``auto`` explains itself per module)."""
    if method == "homo_lumo":
        return (NO_HOMO_LUMO_NOTE if homo_lumo is None else CLOSED_HOMO_LUMO_NOTE,)
    if method == "janela":
        return (NO_WINDOW_GAP_NOTE,)
    return ()


def legend_gap_notes(dataset: BandsDataset, params: BandsParams) -> tuple[str, ...]:
    """Why a gap asked for in a visible legend is not there (the readout's ⚠ lines, never the
    figure); empty when it is there or, in ``auto``, ``dataset.gap_note`` already says why."""
    if not (params.legend_gap and params.show_legend) or gap_entries(dataset, params):
        return ()
    method = gap_method_in_force(params)
    if method != "auto":
        return method_note(method, dataset.homo_lumo)
    if dataset.gap_note:
        return ()
    return (NO_GAP_NOTE if dataset.fermi is not None else NO_COUNT_NOTE,)


def gap_handles(dataset: BandsDataset, params: BandsParams) -> list[Line2D]:
    """Legend entries of the gaps, when the parameter asks for them."""
    if not params.legend_gap:
        return []
    return [gap_handle(gap_label(e.value, e.channel)) for e in gap_entries(dataset, params)]
