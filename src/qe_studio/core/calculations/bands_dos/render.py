"""The bands + DOS figure: bands on the left, the DOS on the right, one energy axis (spec 22)."""

from __future__ import annotations

import numpy as np
from matplotlib.figure import FigureBase
from matplotlib.ticker import MaxNLocator

from ...plotting.draw import bands_dos_axes, finish_joined
from ...plotting.style import PlotStyle
from ..bands import render as bands_render
from ..bands.gap import gap_handles
from ..bands.params import ENERGY_NAMES
from ..params import RenderInfo
from ..pdos import render as pdos_render
from ..readout import signed
from .data import BandsDosDataset
from .params import BandsDosParams, bands_view, dos_view

FERMI_TOLERANCE = 0.05  # eV: E_F of the DOS run this far from the bands' one gets a note
JOIN_CLEARANCE = 0.12  # fraction of the DOS axis, from where the panels meet, without tick labels


class ClearOfJoin(MaxNLocator):
    """The DOS axis' ticks, but none near where it meets the bands: a label there would sit on the
    last k label. A locator (not fixed ticks), so pan and zoom keep it."""

    def tick_values(self, vmin: float, vmax: float):
        ticks = np.asarray(super().tick_values(vmin, vmax))
        low, high = sorted((vmin, vmax))
        return ticks[ticks > low + JOIN_CLEARANCE * (high - low)]


def render_bands_dos(
    figure: FigureBase, dataset: BandsDosDataset, params: BandsDosParams, style: PlotStyle
) -> RenderInfo:
    """One reference for both panels, the bands' (``reference``): the DOS energies are shifted by
    it too, and its Fermi line and filled states follow the bands' E_F."""
    bands, dos = dataset.bands, dataset.dos
    bands_params, dos_params = bands_view(params), dos_view(params)
    ax_bands, ax_dos = bands_dos_axes(figure, style, (1.0, params.dos_width_ratio))
    ref = bands.reference(params.reference)
    band_handles = bands_render.draw_bands(ax_bands, bands, bands_params, style, ref)
    pdos_render.draw_pdos(ax_dos, dos, dos_params, style, ref, bands.fermi, bands.fermi_up_down)
    ax_dos.set_ylabel("")  # the energy is labelled once, on the bands
    ax_dos.xaxis.set_major_locator(ClearOfJoin(nbins="auto"))

    dos_handles = ax_dos.get_legend_handles_labels()[0]
    handles = dos_handles + [h for h in band_handles if h.get_label() not in _labels(dos_handles)]
    channels = bands_render.shown_channels(bands, bands_params)
    # Bands with both channels already tell ↑ (solid) from ↓ (dashed); else the DOS says it.
    overlaid = dos.data.spin_polarized and pdos_render.spin_mode(dos, dos_params) == "overlay"
    if overlaid and len(channels) < 2:
        handles += pdos_render.line_styles(dos_params, style)
    handles += gap_handles(bands, bands_params)  # once: the axis is the same for both panels
    finish_joined(figure, ax_dos if dos_handles else ax_bands, params, handles)
    xlim = bands_render.band_xlim(bands, bands_params, channels[0])
    return RenderInfo(xlim, (params.emin, params.emax), summary(dataset, params), notes(dataset))


def _labels(handles: list) -> set[str]:
    return {h.get_label() for h in handles}


def notes(dataset: BandsDosDataset) -> tuple[str, ...]:
    """What the user should know about pairing these two runs."""
    found = []
    bands_fermi, dos_fermi = dataset.bands.fermi, dataset.dos.fermi("scf")
    delta = None if bands_fermi is None or dos_fermi is None else abs(dos_fermi - bands_fermi)
    if delta is not None and delta > FERMI_TOLERANCE:
        found.append(f"E_F da DOS difere do das bandas em {delta:.3f} eV")
    bands_compound, dos_compound = dataset.bands_compound, dataset.dos.compound
    if bands_compound and dos_compound and bands_compound.key != dos_compound.key:
        found.append(
            f"Bandas ({bands_compound.formula}) e DOS ({dos_compound.formula}) são de compostos "
            "diferentes: a seleção de átomos vale para o composto da DOS"
        )
    return tuple(found)


def summary(dataset: BandsDosDataset, params: BandsDosParams) -> str:
    """The bands' summary (E_F, gap, size) and what the DOS projects."""
    data = dataset.dos.data
    parts = [bands_render.summary(dataset.bands), f"DOS: {len(data.series)} projeções"]
    if params.atoms is not None:
        every = {s.atom for s in data.series}
        parts.append(f"{len(every & set(params.atoms))} de {len(every)} átomos")
    return " · ".join(parts)


def format_coordinates(
    x: float, y: float, axes_index: int, dataset: BandsDosDataset, params: BandsDosParams
) -> str:
    """The bands' readout over the bands; ``E − E_F = … eV · PDOS = … est./eV`` over the DOS."""
    if axes_index == 0:
        return bands_render.format_coordinates(x, y, 0, dataset.bands, bands_view(params))
    name = ENERGY_NAMES.get(params.reference, ENERGY_NAMES["absolute"])
    return f"{name} = {signed(y, '.3f')} eV · PDOS = {signed(x, '.3f')} est./eV"
