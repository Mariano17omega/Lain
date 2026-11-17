"""The "Resultados" of a projwfc.x output in the summary: spilling and Löwdin charges (spec 99).

Numbers are written with four decimals, which is QE's ``f8.4``, with a decimal point.
"""

from __future__ import annotations

from ....i18n import _, ngettext
from ..lowdin import ORBITALS, AtomCharges, LowdinCharges, spilling_is_high
from .model import SummaryRow
from .scan import Facts


def projection_rows(lowdin: LowdinCharges | None, facts: Facts) -> list[SummaryRow]:
    """Empty when there is nothing to show: no block in an output still running (or cut)."""
    if lowdin is None:
        if facts.hit("job_done", first=True) is None:
            return []
        return [
            SummaryRow(_("Cargas de Löwdin"), _("não impressas nesta saída (filowdin ou pawproj)"))
        ]
    rows = []
    if (spilling := lowdin.spilling) is not None:
        level = "warning" if spilling_is_high(spilling) else None
        text = f"{spilling:.4f} ({100 * spilling:.2f} %)"
        rows.append(SummaryRow("Spilling", text, level, lowdin.spilling_line))
    if count := len(lowdin.atoms):
        children = tuple(_atom_row(lowdin, atom) for atom in lowdin.atoms)
        value = ngettext("{count} átomo", "{count} átomos", count).format(count=count)
        rows.append(SummaryRow(_("Cargas de Löwdin"), value, children=children))
        if lowdin.spinor and lowdin.spin_resolved:
            rows.append(
                SummaryRow(
                    _("Nota"),
                    _(
                        "não colinear sem spin-órbita: ↑ e ↓ são as componentes do spinor ao longo de z"
                    ),
                )
            )
    return rows


def _atom_row(lowdin: LowdinCharges, atom: AtomCharges) -> SummaryRow:
    """``1 · Ni``: ``9.8838 e · s 0.9412 · d 8.9426``, with ↑, ↓ and ↑−↓ under it when the run has
    two channels. Only the l the atom has states of: ``lmax_wfc`` is the system's, so QE prints
    ``p = 0.0000`` for an atom without p states."""
    keep = lowdin.channels.get(atom.atom)
    species = lowdin.species.get(atom.atom)
    label = f"{atom.atom} · {species}" if species else str(atom.atom)

    def text(total: float | None, orbitals: dict[str, float], unit: str = " e") -> str:
        parts = [f"{total:.4f}{unit}"] if total is not None else []
        parts += [
            f"{name} {orbitals[name]:.4f}"
            for name in ORBITALS
            if name in orbitals and (keep is None or name in keep)
        ]
        return " · ".join(parts)

    children: tuple[SummaryRow, ...] = ()
    if atom.up is not None or atom.down is not None:
        children = (
            SummaryRow("↑", text(atom.up, atom.orbitals_up), line=atom.line),
            SummaryRow("↓", text(atom.down, atom.orbitals_down), line=atom.line),
            SummaryRow(
                _("Polarização (↑−↓)"),
                text(atom.polarization, atom.orbitals_pol, ""),
                line=atom.line,
            ),
        )
    return SummaryRow(label, text(atom.total, atom.orbitals), line=atom.line, children=children)
