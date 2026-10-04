"""Band structure figure, cursor readout, tick labels and the one-line summary."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator

from ...plotting.draw import finish, finish_side, new_axes, side_axes
from ...plotting.style import PlotStyle
from ...qe.pw_input import format_kpoint_label
from ..params import RenderInfo
from ..readout import nearest_tick_label, signed
from .data import BandsDataset, valence_mask
from .gap import gap_entries, gap_handles
from .params import ENERGY_NAMES, Y_LABELS, BandsParams

SYMBOL = {"up": "↑", "down": "↓"}
FERMI_DASH = (0, (5, 3))
DOWN_DASH = (0, (4, 2))  # the ↓ channel, when both share an axes


def render_bands(
    figure: Figure, dataset: BandsDataset, params: BandsParams, style: PlotStyle
) -> RenderInfo:
    if dataset.spin:
        return _render_spin(figure, dataset, params, style)
    return _render_plain(figure, dataset, params, style)


def shown_channels(dataset: BandsDataset, params: BandsParams) -> list[str]:
    """The spin channels drawn (``["up"]`` for a run without spin)."""
    if not dataset.spin:
        return ["up"]
    return {"up": ["up"], "down": ["down"]}.get(params.spin_channels, ["up", "down"])


def _render_plain(
    figure: Figure, dataset: BandsDataset, params: BandsParams, style: PlotStyle
) -> RenderInfo:
    ax = new_axes(figure, style)
    ref = dataset.reference(params.reference)
    x = dataset.bands.x
    energies = dataset.bands.energies - ref
    up = dataset.edges.get("up")  # a spin run whose ↓ channel is missing
    n_occupied = dataset.n_occupied if up is None else up.n_occupied
    if n_occupied is not None:
        valence = np.arange(len(energies)) < n_occupied
    elif dataset.fermi is not None:
        valence = energies.max(axis=1) <= dataset.fermi - ref
    else:
        valence = np.zeros(len(energies), dtype=bool)
    handles = []
    for mask, color, label in (
        (valence, params.valence_color, "Valência"),
        (~valence, params.conduction_color, "Condução"),
    ):
        if mask.any():
            segments = [np.column_stack([x, e]) for e in energies[mask]]
            ax.add_collection(LineCollection(segments, colors=color, linewidths=params.line_width))
            handles.append(Line2D([], [], color=color, lw=params.line_width, label=label))

    ticks, labels = merged_ticks(dataset.ticks, tick_labels(dataset, params))
    if params.show_hs_lines:
        for tick in ticks[1:-1]:
            ax.axvline(tick, color=style.guide, lw=0.7, zorder=0)
    if dataset.fermi is not None and params.show_fermi_line:
        ax.axhline(
            dataset.fermi - ref,
            color=params.fermi_color,
            lw=0.9,
            ls=(0, (5, 3)),
            zorder=1,
        )
        handles.append(
            Line2D([], [], color=params.fermi_color, lw=0.9, ls=(0, (5, 3)), label="$E_F$")
        )
    handles += gap_handles(dataset, params)
    ax.set_xticks(ticks, labels)
    xlim = (
        params.xmin if params.xmin is not None else float(x[0]),
        params.xmax if params.xmax is not None else float(x[-1]),
    )
    ax.set_xlim(*xlim)
    ax.set_ylim(params.emin, params.emax)
    ax.set_ylabel(Y_LABELS.get(params.reference, Y_LABELS["absolute"]))
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(axis="x", which="both", length=0, pad=6)
    ax.tick_params(axis="y", which="both", right=True)
    finish(figure, ax, params, handles)
    return RenderInfo(xlim, (params.emin, params.emax), summary(dataset))


# -- spin (two channels) -------------------------------------------------------------------------
def _render_spin(
    figure: Figure, dataset: BandsDataset, params: BandsParams, style: PlotStyle
) -> RenderInfo:
    """↑ and ↓ overlaid on one axes (↓ dashed) or in two panels side by side (``sharey``)."""
    channels = shown_channels(dataset, params)
    ref = dataset.reference(params.reference)
    side = len(channels) == 2 and params.spin_layout == "side"
    if side:
        axes = side_axes(figure, style, 2)
        panels = [(ax, [channel]) for ax, channel in zip(axes, channels, strict=True)]
    else:
        axes = [new_axes(figure, style)]
        panels = [(axes[0], channels)]

    ticks, labels = merged_ticks(dataset.ticks, tick_labels(dataset, params))
    first = dataset.band_data(channels[0])
    assert first is not None
    path = first.x
    xlim = (
        params.xmin if params.xmin is not None else float(path[0]),
        params.xmax if params.xmax is not None else float(path[-1]),
    )
    color_handles: list = []
    fermi_handles: list = []
    for ax, on_axes in panels:
        for channel in on_axes:
            dashed = len(on_axes) == 2 and channel == "down"
            _add_handles(color_handles, _draw_channel(ax, dataset, channel, params, ref, dashed))
        _add_handles(fermi_handles, _fermi_lines(ax, dataset, on_axes, params, ref))
        if params.show_hs_lines:
            for tick in ticks[1:-1]:
                ax.axvline(tick, color=style.guide, lw=0.7, zorder=0)
        ax.set_xticks(ticks, labels)
        ax.set_xlim(*xlim)
        ax.set_ylim(params.emin, params.emax)
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.tick_params(axis="x", which="both", length=0, pad=6)
        ax.tick_params(axis="y", which="both", right=True)
        if side:
            ax.set_title(f"Spin {SYMBOL[on_axes[0]]}", fontsize=params.font_size)
    axes[0].set_ylabel(Y_LABELS.get(params.reference, Y_LABELS["absolute"]))
    # Side by side, the panel titles already name the channels.
    handles = [] if side and params.spin_coloring == "channel" else color_handles
    if len(channels) == 2 and not side:
        handles += _channel_styles(params, style)
    handles += fermi_handles
    handles += gap_handles(dataset, params)
    if side:
        finish_side(figure, axes, params, handles)
    else:
        finish(figure, axes[0], params, handles)
    return RenderInfo(xlim, (params.emin, params.emax), summary(dataset))


def _add_handles(handles: list, new: list) -> None:
    """Legend entries once per label (both panels or channels may bring the same one)."""
    known = {h.get_label() for h in handles}
    handles += [h for h in new if h.get_label() not in known]


def _channel_fermi(dataset: BandsDataset, channel: str) -> float | None:
    if dataset.fermi_up_down is not None:
        return dataset.fermi_up_down[0 if channel == "up" else 1]
    return dataset.fermi


def _draw_channel(
    ax: Axes, dataset: BandsDataset, channel: str, params: BandsParams, ref: float, dashed: bool
) -> list[Line2D]:
    """The bands of one channel; legend handles for its color groups."""
    band = dataset.band_data(channel)
    assert band is not None
    energies = band.energies - ref
    linestyle = DOWN_DASH if dashed else "-"
    if params.spin_coloring == "occupation":
        valence = _valence(dataset, channel, band.energies)
        groups = [
            (valence, params.valence_color, "Valência"),
            (~valence, params.conduction_color, "Condução"),
        ]
    else:
        color = params.up_color if channel == "up" else params.down_color
        groups = [(np.ones(len(energies), dtype=bool), color, f"Spin {SYMBOL[channel]}")]
    handles = []
    for mask, color, label in groups:
        if not mask.any():
            continue
        segments = [np.column_stack([band.x, e]) for e in energies[mask]]
        ax.add_collection(
            LineCollection(
                segments, colors=color, linewidths=params.line_width, linestyles=linestyle
            )
        )
        handles.append(Line2D([], [], color=color, lw=params.line_width, ls=linestyle, label=label))
    return handles


def _valence(dataset: BandsDataset, channel: str, energies: np.ndarray) -> np.ndarray:
    """Valence bands of one channel: by electron count when the edges came from it (fixed
    occupations), else the bands below the channel's E_F."""
    edges = dataset.edges.get(channel)
    if edges is not None and edges.n_occupied is not None:
        return np.arange(len(energies)) < edges.n_occupied
    fermi = _channel_fermi(dataset, channel)
    if fermi is None:
        return np.zeros(len(energies), dtype=bool)
    return valence_mask(energies, fermi)


def _channel_styles(params: BandsParams, style: PlotStyle) -> list[Line2D]:
    """Legend entries telling ↑ (solid) from ↓ (dashed) when colors encode occupation instead."""
    if params.spin_coloring == "channel":
        return []
    return [
        Line2D([], [], color=style.text, lw=params.line_width, ls="-", label="Spin ↑"),
        Line2D([], [], color=style.text, lw=params.line_width, ls=DOWN_DASH, label="Spin ↓"),
    ]


def _fermi_lines(
    ax: Axes, dataset: BandsDataset, on_axes: list[str], params: BandsParams, ref: float
) -> list[Line2D]:
    """One E_F line, or (fixed magnetization) one per channel: ↑ solid, ↓ dashed."""
    if dataset.fermi is None or not params.show_fermi_line:
        return []
    if dataset.fermi_up_down is None:
        ax.axhline(dataset.fermi - ref, color=params.fermi_color, lw=0.9, ls=FERMI_DASH, zorder=1)
        return [Line2D([], [], color=params.fermi_color, lw=0.9, ls=FERMI_DASH, label="$E_F$")]
    handles = []
    for channel in on_axes:
        value = _channel_fermi(dataset, channel)
        assert value is not None
        ls = "-" if channel == "up" else FERMI_DASH
        ax.axhline(value - ref, color=params.fermi_color, lw=0.9, ls=ls, zorder=1)
        label = f"$E_F$ {SYMBOL[channel]}"
        handles.append(Line2D([], [], color=params.fermi_color, lw=0.9, ls=ls, label=label))
    return handles


def format_coordinates(
    x: float, y: float, axes_index: int, dataset: BandsDataset, params: BandsParams
) -> str:
    """``k = 0.5120 · E − E_F = −1.234 eV``, plus the label of a high-symmetry point near."""
    path = dataset.bands.x
    low = params.xmin if params.xmin is not None else float(path[0])
    high = params.xmax if params.xmax is not None else float(path[-1])
    ticks, labels = merged_ticks(dataset.ticks, tick_labels(dataset, params))
    name = ENERGY_NAMES.get(params.reference, ENERGY_NAMES["absolute"])
    text = f"k = {x:.4f} · {name} = {signed(y, '.3f')} eV"
    near = nearest_tick_label(x, ticks, labels, high - low)
    return f"{text} · {near}" if near else text


def tick_labels(dataset: BandsDataset, params: BandsParams) -> list[str]:
    raw = dataset.labels
    if params.labels.strip():
        typed = [part.strip() for part in params.labels.split(",")]
        raw = (typed + [""] * len(dataset.ticks))[: len(dataset.ticks)]
    return [format_kpoint_label(label) for label in raw]


def summary(dataset: BandsDataset) -> str:
    parts = []
    if dataset.fermi is not None:
        if dataset.fermi_up_down is not None and dataset.spin:
            up, down = dataset.fermi_up_down
            parts.append(f"E_F↑ = {up:.4f} eV · E_F↓ = {down:.4f} eV")
        else:
            name = "E_F" if dataset.fermi_kind in ("fermi", "spin_fermi") else "HOMO"
            parts.append(f"{name} = {dataset.fermi:.4f} eV")
    if dataset.spin:
        parts.append("spin polarizado")
        parts += _spin_gaps(dataset)
        if dataset.magnetization is not None:
            parts.append(f"M = {dataset.magnetization:.2f} μB/célula")
    elif dataset.edges:  # spin run with the ↑ channel only: not a verdict on the whole system
        parts += _spin_gaps(dataset)
    elif gaps := gap_entries(dataset):
        parts.append(f"E_gap = {gaps[0].value:.3f} eV")
    elif dataset.fermi is not None:
        parts.append("metálico")
    parts.append(f"{dataset.bands.n_bands} bandas × {dataset.bands.n_kpoints} pontos k")
    return " · ".join(parts)


def _spin_gaps(dataset: BandsDataset) -> list[str]:
    """``gap ↑ 1.234 eV``, ``↓ metálico`` per channel, and the global gap when both have one."""
    parts = []
    gaps = {entry.channel: entry.value for entry in gap_entries(dataset)}
    for channel, edges in dataset.edges.items():
        if channel in gaps:
            parts.append(f"gap {SYMBOL[channel]} {gaps[channel]:.3f} eV")
        elif edges.metallic:
            parts.append(f"{SYMBOL[channel]} metálico")
    if "global" in gaps:
        parts.append(f"gap global {gaps['global']:.3f} eV")
    return parts


def merged_ticks(ticks: list[float], labels: list[str]) -> tuple[list[float], list[str]]:
    """Merge coincident ticks (path discontinuities) into ``A|B`` labels."""
    out_ticks: list[float] = []
    out_labels: list[str] = []
    for tick, label in zip(ticks, labels, strict=False):
        if out_ticks and abs(tick - out_ticks[-1]) < 1e-4:
            if label and label != out_labels[-1]:
                out_labels[-1] = f"{out_labels[-1]}|{label}" if out_labels[-1] else label
            continue
        out_ticks.append(tick)
        out_labels.append(label)
    return out_ticks, out_labels
