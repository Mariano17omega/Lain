"""The curves of a PDOS plot as columns (spec 32 R4): the series ``draw_pdos`` draws, in its order."""

from __future__ import annotations

from ...plotting.table import Column, PlotTable
from ...qe import projwfc
from .data import PdosDataset
from .params import PdosParams
from .render import reference, series_label, spin_mode, total_curve

DOS_UNIT = "estados/eV"


def pdos_table(
    dataset: PdosDataset,
    params: PdosParams,
    ref: float | None = None,
    energy_name: str | None = None,
) -> PlotTable:
    """The energy minus ``ref`` (the plot's own reference unless the caller, bands + DOS, gives the
    bands'; ``energy_name`` names it) and a column per curve drawn: the total if shown, then every
    group of the chosen atoms that is not hidden. A spin PDOS follows ``spin_mode``: ↑ and ↓ columns
    (the ↓ of ``mirror`` is negative, as drawn), one channel, or their sum."""
    data = dataset.data
    if ref is None:
        ref = reference(dataset, params)
    if energy_name is None:
        energy_name = "E − E_F" if ref else "E"
    columns = [Column(f"{energy_name} (eV)", data.energy - ref)]
    mode = spin_mode(dataset, params)
    spin = data.spin_polarized

    def named(label: str, channel: str = "", note: str = "") -> str:
        unit = f"{DOS_UNIT}, {note}" if note else DOS_UNIT
        return f"{label} {channel} ({unit})" if channel else f"{label} ({unit})"

    def add(curve: projwfc.Channel, label: str) -> None:
        down = curve.down if spin else None
        if mode == "down":
            if down is not None:
                columns.append(Column(named(label, "↓"), down))
        elif mode == "sum":
            columns.append(
                Column(named(label, "↑+↓"), curve.up if down is None else curve.up + down)
            )
        else:  # mirror, overlay, up
            columns.append(Column(named(label, "↑" if spin else ""), curve.up))
            if down is not None and mode == "mirror":
                columns.append(Column(named(label, "↓", "espelhado"), -down))
            elif down is not None and mode == "overlay":
                columns.append(Column(named(label, "↓"), down))

    total, total_label = total_curve(data, params)
    if params.show_total and total is not None:
        add(total, total_label)
    for key, curve in projwfc.aggregate(data, params.grouping, params.atoms).items():
        label = series_label(key)
        if label not in params.hidden_series:
            add(curve, label)
    return PlotTable.of(columns)
