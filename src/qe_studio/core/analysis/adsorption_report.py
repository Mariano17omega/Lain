"""The report of "Calcular adsorção…" (spec 78 R2, spec 97 R5): a Markdown file beside the outputs.

It holds the table (energy and level of theory of each output), the equation, the result in Ry, eV and
kJ/mol, the warnings of ``consistency.check`` (or the sentence that there is none) and its notes. It is
written in the interface's language, like ``geracao.md``, and never over a file (``_2``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from ...i18n import _
from ..files.unique_names import write_new
from .adsorption_energy import EnergyRow, Outcome
from .consistency import check
from .level_of_theory import cutoffs_text, mesh_text, occupations_text, spin_text, xc_text

REPORT_PREFIX = "energia_ads_"
NAME_LIMIT = 200  # characters of the report's name before ``.md``

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # as ``calc_create/types/files.unit_stem``


def report_text(rows: Sequence[EnergyRow], equation: str, outcome: Outcome) -> str:
    header = (
        _("Prefixo"),
        _("Arquivo"),
        _("Átomos"),
        _("Energia total (Ry)"),
        _("Cutoffs (Ry)"),
        _("Funcional"),
        _("Ocupações"),
        "Spin",
        _("Malha k"),
    )
    lines = [
        _("# Energia de adsorção"),
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for row in rows:
        atoms = "" if row.atoms is None else str(row.atoms)
        energy = f"{row.energy_ry:.8f}" if row.energy_ry is not None else f"— ({row.problem})"
        theory = row.theory
        cells = (
            row.name,
            row.path.name,
            atoms,
            energy,
            cutoffs_text(theory),
            xc_text(theory),
            occupations_text(theory),
            spin_text(theory),
            mesh_text(theory),
        )
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", _("## Equação"), "", "```", equation.strip(), "```", ""]
    lines.append(_("**Resultado**: {text}").format(text=outcome.text))
    consistency = check(equation, rows)
    lines += ["", _("## Avisos"), ""]
    if consistency.warnings:
        lines += [f"- {warning}" for warning in consistency.warnings]
    else:
        lines.append(
            _(
                "Nenhum aviso nas condições conferidas (cutoffs, funcional, dispersão, pseudopotenciais, ocupações, spin, célula, malha k e átomos)."
            )
        )
    lines += ["", _("## Notas"), ""]
    lines += [f"- {note}" for note in consistency.notes]
    return "\n".join(lines) + "\n"


def report_name(rows: Sequence[EnergyRow]) -> str:
    """``energia_ads_<prefix1>_<prefix2>….md``, the prefixes in the table's order."""
    stems = (_UNSAFE.sub("_", row.prefix.strip()) or "pwscf" for row in rows)
    return (REPORT_PREFIX + "_".join(stems))[:NAME_LIMIT] + ".md"


def save_report(folder: Path, rows: Sequence[EnergyRow], equation: str, outcome: Outcome) -> Path:
    """Write the report into ``folder`` (worker); a name taken gets ``_2``, never overwritten."""
    text = report_text(rows, equation, outcome)
    return write_new(Path(folder) / report_name(rows), text, first=2)
