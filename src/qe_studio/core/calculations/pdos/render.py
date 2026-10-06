"""PDOS figure, series colors, cursor readout and the one-line summary."""

from __future__ import annotations

import colorsys

import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import to_hex, to_rgb
from matplotlib.figure import FigureBase
from matplotlib.lines import Line2D

from ...config import DEFAULT_ORBITAL_COLORS
from ...plotting.draw import finish, new_axes
from ...plotting.gap_label import gap_handle, gap_label
from ...plotting.style import PlotStyle
from ...qe import projwfc
from ..params import RenderInfo
from ..readout import signed
from .atoms import notes
from .data import PdosDataset
from .params import PdosParams


def series_label(key: tuple[str, str]) -> str:
    species, orbital = key
    return " ".join(part for part in (species, orbital) if part)


def _shade(color: str, index: int) -> str:
    """Distinguish species sharing an orbital color by stepping lightness."""
    if index == 0:
        return color
    h, lightness, s = colorsys.rgb_to_hls(*to_rgb(color))
    step = 0.14 * ((index + 1) // 2) * (1 if index % 2 else -1)
    return to_hex(colorsys.hls_to_rgb(h, min(max(lightness + step, 0.15), 0.85), s))


def series_colors(dataset: PdosDataset, params: PdosParams, style: PlotStyle) -> dict[str, str]:
    """Color of every group for the current grouping (user overrides first). A species with an
    entry in ``atomos_colors`` takes it (shaded per orbital when grouped by orbital too), else the
    orbital color shaded by species, else the palette."""
    orbital_colors = {**DEFAULT_ORBITAL_COLORS, **params.orbital_colors}
    species_index = {name: i for i, name in enumerate(dataset.data.species)}
    # Colors follow the order of *all* the atoms, so choosing atoms never recolors a group; only
    # the groups that still have a series are listed.
    shown = projwfc.aggregate(dataset.data, params.grouping, params.atoms)
    colors = {}
    for i, key in enumerate(projwfc.aggregate(dataset.data, params.grouping)):
        if key not in shown:
            continue
        label = series_label(key)
        species, orbital = key
        if species in params.atomos_colors:
            color = _shade(
                params.atomos_colors[species], max(projwfc.ORBITAL_ORDER.find(orbital), 0)
            )
        elif orbital:
            color = _shade(orbital_colors[orbital], species_index.get(species, 0))
        else:
            color = style.palette[i % len(style.palette)]
        colors[label] = params.series_colors.get(label, color)
    return colors


SPIN_MODES = ("mirror", "overlay", "up", "down", "sum")
FERMI_DASH = (0, (5, 3))
DOWN_DASH = (0, (4, 2))  # the ↓ channel overlaid on ↑


def spin_mode(dataset: PdosDataset, params: PdosParams) -> str:
    """The drawing mode: ``mirror`` (the original look) unless the PDOS has two channels."""
    if dataset.data.spin_polarized and params.spin_mode in SPIN_MODES:
        return params.spin_mode
    return "mirror"


def reference(dataset: PdosDataset, params: PdosParams) -> float:
    """The energy the plot is measured from: E_F of the chosen run, or 0 (absolute energies)."""
    fermi = dataset.fermi(params.fermi_source)
    return fermi if params.shift_to_fermi and fermi is not None else 0.0


def render_pdos(
    figure: FigureBase, dataset: PdosDataset, params: PdosParams, style: PlotStyle
) -> RenderInfo:
    ax = new_axes(figure, style)
    fermi = dataset.fermi(params.fermi_source)
    ref = reference(dataset, params)
    pair = dataset.fermi_channels(params.fermi_source)
    dos_lim = draw_pdos(ax, dataset, params, style, ref, fermi, pair)
    handles = None
    if dataset.data.spin_polarized and spin_mode(dataset, params) == "overlay":
        handles = ax.get_legend_handles_labels()[0] + line_styles(params, style)
    if params.legend_gap and dataset.gap is not None:
        if handles is None:
            handles = ax.get_legend_handles_labels()[0]
        handles.append(gap_handle(gap_label(dataset.gap.value, approx=dataset.gap.source == "dos")))
    finish(figure, ax, params, handles)
    e_lim = (params.emin, params.emax)
    xlim, ylim = (dos_lim, e_lim) if params.orientation == "vertical" else (e_lim, dos_lim)
    return RenderInfo(xlim, ylim, summary(dataset, params), notes(dataset))


def draw_pdos(
    ax: Axes,
    dataset: PdosDataset,
    params: PdosParams,
    style: PlotStyle,
    ref: float,
    fermi: float | None,
    pair: tuple[float, float] | None,
) -> tuple[float, float]:
    """The PDOS on ``ax``, energies minus ``ref``; ``fermi`` (absolute) places the Fermi line and
    the filled occupied states, ``pair`` the line of each channel (fixed magnetization). Returns
    the limits of the DOS axis; the legend is the caller's."""
    data = dataset.data
    energy = data.energy - ref
    fermi_rel = None if fermi is None else fermi - ref
    # E_F of each channel relative to ``ref`` (equal unless the run fixed the magnetization).
    fermi_by = {"up": fermi_rel, "down": fermi_rel, "sum": fermi_rel}
    if pair is not None:
        fermi_by.update(up=pair[0] - ref, down=pair[1] - ref)
    window = (energy >= params.emin) & (energy <= params.emax)
    vertical = params.orientation == "vertical"
    spin = data.spin_polarized
    mode = spin_mode(dataset, params)
    peak = 0.0

    def draw(
        values: np.ndarray,
        color: str,
        label: str | None,
        width: float,
        alpha: float,
        channel_fermi: float | None,
        ls: object = "-",
        fill: bool = True,
    ):
        nonlocal peak
        if window.any():
            peak = max(peak, float(np.abs(values[window]).max()))
        if vertical:
            ax.plot(values, energy, color=color, lw=width, ls=ls, label=label)
        else:
            ax.plot(energy, values, color=color, lw=width, ls=ls, label=label)
        if fill and params.fill_occupied and channel_fermi is not None:
            occupied = energy <= channel_fermi
            filler = ax.fill_betweenx if vertical else ax.fill_between
            filler(energy, 0, values, where=occupied, color=color, alpha=alpha, lw=0)

    def channel(ch: projwfc.Channel, color: str, label: str, width: float, alpha: float):
        down = ch.down if spin else None
        if mode == "down":
            if down is not None:
                draw(down, color, label, width, alpha, fermi_by["down"])
        elif mode == "sum":
            total = ch.up if down is None else ch.up + down
            draw(total, color, label, width, alpha, fermi_by["sum"])
        else:  # mirror, overlay, up
            draw(ch.up, color, label, width, alpha, fermi_by["up"])
            if down is not None and mode == "mirror":
                draw(-down, color, None, width, alpha, fermi_by["down"])
            elif down is not None and mode == "overlay":
                draw(down, color, None, width, alpha, None, ls=DOWN_DASH, fill=False)

    total, total_label = total_curve(data, params)
    if params.show_total and total is not None:
        channel(total, params.total_color or style.total_dos, total_label, params.line_width, 0.12)
    colors = series_colors(dataset, params, style)
    for key, ch in projwfc.aggregate(data, params.grouping, params.atoms).items():
        label = series_label(key)
        if label not in params.hidden_series:
            channel(ch, colors[label], label, params.line_width, 0.22)

    mirrored = spin and mode == "mirror"
    top = params.dos_max if params.dos_max else (peak * 1.08 or 1.0)
    dos_lim = (-top if mirrored else 0.0, top)
    e_lim = (params.emin, params.emax)
    e_label = r"$E - E_F$ (eV)" if ref else r"$E$ (eV)"
    dos_label = "PDOS (estados/eV)"
    guide = {"color": style.guide, "lw": 0.7, "zorder": 0}
    if vertical:
        ax.set_xlim(*dos_lim)
        ax.set_ylim(*e_lim)
        ax.set_xlabel(dos_label)
        ax.set_ylabel(e_label)
        if mirrored:
            ax.axvline(0, **guide)
    else:
        ax.set_xlim(*e_lim)
        ax.set_ylim(*dos_lim)
        ax.set_xlabel(e_label)
        ax.set_ylabel(dos_label)
        if mirrored:
            ax.axhline(0, **guide)
    if params.show_fermi_line:
        _fermi_lines(ax, params, vertical, fermi_rel, fermi_by if pair else None, mode)
    if mirrored:
        _channel_marks(ax, params, style, vertical)
    ax.minorticks_on()
    ax.tick_params(which="both", top=True, right=True)
    return dos_lim


def total_curve(data: projwfc.PdosData, params: PdosParams) -> tuple[projwfc.Channel | None, str]:
    """The "DOS total" curve and its legend label. pdos_tot holds every atom, which would mislead
    next to a subset of them: then it is the sum of what is drawn."""
    if params.atoms is not None:
        return projwfc.selected_total(data, params.atoms), "Soma dos átomos selecionados"
    return data.total, "Total (Σ PDOS)" if data.total_is_sum else "Total"


def _fermi_lines(
    ax: Axes,
    params: PdosParams,
    vertical: bool,
    fermi_rel: float | None,
    by_channel: dict[str, float | None] | None,
    mode: str,
) -> None:
    """The Fermi line; with two Fermi energies one per channel shown (↑ solid, ↓ dashed)."""
    if fermi_rel is None:
        return
    draw = ax.axhline if vertical else ax.axvline
    style = {"color": params.fermi_color, "lw": 0.9}
    if by_channel is None or mode == "sum":
        draw(fermi_rel, ls=FERMI_DASH, **style)
        return
    shown = {"up": ["up"], "down": ["down"]}.get(mode, ["up", "down"])
    for channel in shown:
        value = by_channel[channel]
        if value is not None:
            draw(value, ls="-" if channel == "up" else FERMI_DASH, **style)


def _channel_marks(ax: Axes, params: PdosParams, style: PlotStyle, vertical: bool) -> None:
    """A discreet ↑ / ↓ on each side of the zero line of a mirrored PDOS."""
    mark = {"color": style.guide, "fontsize": params.font_size, "transform": ax.transAxes}
    if vertical:  # the DOS is on X: ↑ right of zero, ↓ left of it
        ax.text(0.97, 0.98, "↑", ha="right", va="top", **mark)
        ax.text(0.03, 0.98, "↓", ha="left", va="top", **mark)
    else:  # the DOS is on Y: ↑ above zero, ↓ below it
        ax.text(0.015, 0.97, "↑", ha="left", va="top", **mark)
        ax.text(0.015, 0.03, "↓", ha="left", va="bottom", **mark)


def line_styles(params: PdosParams, style: PlotStyle) -> list[Line2D]:
    """Legend entries for the two channels of an overlaid PDOS."""
    return [
        Line2D([], [], color=style.text, lw=params.line_width, ls="-", label="↑ contínua"),
        Line2D([], [], color=style.text, lw=params.line_width, ls=DOWN_DASH, label="↓ tracejada"),
    ]


def format_coordinates(
    x: float, y: float, axes_index: int, dataset: PdosDataset, params: PdosParams
) -> str:
    """``E − E_F = −1.234 eV · PDOS = 0.873 est./eV``; the DOS is on X when vertical."""
    energy, dos = (y, x) if params.orientation == "vertical" else (x, y)
    shifted = params.shift_to_fermi and dataset.fermi(params.fermi_source) is not None
    name = "E − E_F" if shifted else "E"
    return f"{name} = {signed(energy, '.3f')} eV · PDOS = {signed(dos, '.3f')} est./eV"


def summary(dataset: PdosDataset, params: PdosParams) -> str:
    parts = []
    fermi = dataset.fermi(params.fermi_source)
    source = params.fermi_source.upper()
    if (pair := dataset.fermi_channels(params.fermi_source)) is not None:
        parts.append(f"E_F↑ = {pair[0]:.4f} eV · E_F↓ = {pair[1]:.4f} eV ({source})")
    elif fermi is not None:
        parts.append(f"E_F = {fermi:.4f} eV ({source})")
    data = dataset.data
    parts.append(f"{len(data.series)} projeções · {len(data.species)} espécies")
    if params.atoms is not None:
        every = {s.atom for s in data.series}
        parts.append(f"{len(every & set(params.atoms))} de {len(every)} átomos")
    if data.spin_polarized:
        parts.append("spin polarizado")
        if dataset.magnetization is not None:
            parts.append(f"M = {dataset.magnetization:.2f} μB/célula")
    return " · ".join(parts)
