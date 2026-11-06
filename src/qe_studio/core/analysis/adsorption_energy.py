"""The energies of SCF outputs and the user's equation over them (spec 78 R2): "Calcular adsorção…".

Each output gives its final total energy (the ``!`` line, ``core/qe/scf.read_scf``), its number of
atoms and its ``prefix``: the one of the input with the same name, else the one of its ``output data
dir …/<prefix>.save/`` line, else the file's name. The rows are ordered by the heuristic of the
request (most atoms first: the complex, then the substrate, then the adsorbates), which only fills in
the default equation; the user edits it freely. A variable is written ``E(<name>)``, so a ``prefix``
with ``-`` or ``.`` is never read as a subtraction. The report is a Markdown file beside the outputs,
in the interface's language like ``geracao.md``, and never overwrites one (``_2``).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ...i18n import _
from .. import cancel
from ..files.unique_names import write_new
from ..qe.pairing import same_name_input
from ..qe.pw_input import read_input
from ..qe.scf import read_scf
from .expression import ExpressionError, evaluate, incomplete

# RYTOEV of QE 7.1's Modules/constants.f90: AUTOEV / 2 = HARTREE_SI / ELECTRONVOLT_SI / 2, with
# HARTREE_SI = 4.3597447222071E-18 J and ELECTRONVOLT_SI = 1.602176634E-19 J (NIST 2018).
RY_TO_EV = 13.605693122994
DEFAULT_NAME = "E_ads"
REPORT_PREFIX = "energia_ads_"
NAME_LIMIT = 200  # characters of the report's name before ``.md``
NO_ENERGY = _("sem energia total final (o SCF não convergiu ou a saída está incompleta)")

_ATOMS = re.compile(r"number of atoms/cell\s*=\s*(\d+)")
_SAVE_DIR = re.compile(r"output data dir\s+\S*?([^/\s]+)\.save/")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # as ``calc_create/types/files.unit_stem``
_WORD = re.compile(r"[A-Za-z0-9_]")


class Role(Enum):
    COMPLEX = "complex"
    SUBSTRATE = "substrate"
    ADSORBATE = "adsorbate"


ROLE_LABELS = {
    Role.COMPLEX: _("Complexo"),
    Role.SUBSTRATE: _("Substrato"),
    Role.ADSORBATE: _("Adsorvato"),
}


@dataclass(frozen=True)
class EnergyRow:
    path: Path
    prefix: str
    name: str  # the variable: the prefix, ``<prefix>_2``… when two outputs share it
    atoms: int | None
    energy_ry: float | None
    problem: str | None = None  # why the row has no energy: it stays out of the equation
    role: Role | None = None  # by the heuristic; None for a row without energy


@dataclass(frozen=True)
class Outcome:
    name: str
    value_ry: float | None
    error: str | None = None

    @property
    def text(self) -> str:
        if self.value_ry is None:
            return self.error or ""
        return result_text(self.name, self.value_ry)


def role_label(role: Role | None) -> str:
    return "" if role is None else ROLE_LABELS[role]


# -- reading ----------------------------------------------------------------------------------------
def _scan(path: Path) -> tuple[int | None, str | None]:
    """The first ``number of atoms/cell`` and the last ``output data dir`` prefix, in one pass."""
    atoms, save = None, None
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in cancel.checked(handle):
            if atoms is None and (match := _ATOMS.search(line)):
                atoms = int(match.group(1))
            elif "output data dir" in line and (match := _SAVE_DIR.search(line)):
                save = match.group(1)
    return atoms, save


def _prefix(path: Path, save: str | None) -> str:
    paired = same_name_input(path)
    parsed = read_input(paired) if paired is not None else None
    prefix = parsed.get("control", "prefix") if parsed is not None else None
    if isinstance(prefix, str) and prefix.strip():
        return prefix.strip()
    return save or path.stem


def read_row(path: Path) -> EnergyRow:
    path = Path(path)
    atoms, save = _scan(path)
    energy = read_scf(path).final_energy_ry
    problem = None if energy is not None else NO_ENERGY
    return EnergyRow(path, _prefix(path, save), "", atoms, energy, problem)


def read_rows(paths: Iterable[Path]) -> list[EnergyRow]:
    """The rows of ``paths`` in the table's order, with their variable names and roles (worker)."""
    rows = []
    for path in paths:
        cancel.check()
        rows.append(read_row(path))
    return arrange(rows)


def arrange(rows: Iterable[EnergyRow]) -> list[EnergyRow]:
    """Most atoms first, a tie by the file's name; unique names in that order; the roles."""
    ordered = sorted(rows, key=lambda row: (-(row.atoms or 0), row.path.name))
    taken: set[str] = set()
    with_energy = 0
    out = []
    for row in ordered:
        name, n = row.prefix, 1
        while name in taken:
            n += 1
            name = f"{row.prefix}_{n}"
        taken.add(name)
        role = None
        if row.energy_ry is not None:
            role = (
                (Role.COMPLEX, Role.SUBSTRATE)[with_energy] if with_energy < 2 else Role.ADSORBATE
            )
            with_energy += 1
        out.append(
            EnergyRow(row.path, row.prefix, name, row.atoms, row.energy_ry, row.problem, role)
        )
    return out


# -- the equation -----------------------------------------------------------------------------------
def default_equation(rows: Sequence[EnergyRow]) -> str:
    """``E_ads = E(complex) - E(substrate) - E(adsorbate)…``; ``E_ads = `` with fewer than two."""
    names = [row.name for row in rows if row.energy_ry is not None]
    if len(names) < 2:
        return f"{DEFAULT_NAME} = "
    return f"{DEFAULT_NAME} = " + " - ".join(f"E({name})" for name in names)


def parse_equation(text: str) -> tuple[str, str]:
    """(name, expression): an optional ``<name> =`` at the start, ``E_ads`` without one."""
    if "=" not in text:
        return DEFAULT_NAME, text.strip()
    name, expression = text.split("=", 1)
    return name.strip() or DEFAULT_NAME, expression.strip()


def substitute(expression: str, rows: Sequence[EnergyRow]) -> tuple[str, dict[str, float]]:
    """``expression`` with each ``E(<name>)`` replaced by an internal name, and their values. The
    internal names start with what the text does not hold, as the parser reads it (NFKC), so a name
    the user typed is never read as one: it stays unknown."""
    energies = {row.name: row.energy_ry for row in rows if row.energy_ry is not None}
    empty = {row.name for row in rows if row.energy_ry is None}
    stem, plain = "_v", unicodedata.normalize("NFKC", expression)
    while stem in plain:
        stem = "_" + stem
    internal: dict[str, str] = {}
    values: dict[str, float] = {}
    out, i = [], 0
    while (start := expression.find("E(", i)) >= 0:
        if start > 0 and _WORD.match(expression[start - 1]):  # ``XE(`` is no variable
            out.append(expression[i : start + 2])
            i = start + 2
            continue
        depth, end = 1, start + 2
        while end < len(expression) and depth:
            depth += {"(": 1, ")": -1}.get(expression[end], 0)
            end += 1
        if depth:
            raise incomplete()
        name = expression[start + 2 : end - 1].strip()
        if name in empty:
            raise ExpressionError(_("E({name}): sem energia total final").format(name=name))
        if name not in energies:
            raise ExpressionError(_("E({name}): prefixo desconhecido").format(name=name))
        key = internal.setdefault(name, f"{stem}{len(internal)}")
        values[key] = energies[name]  # type: ignore[assignment]
        out.append(expression[i:start])
        out.append(f" {key} ")
        i = end
    out.append(expression[i:])
    return "".join(out), values


def calculate(equation: str, rows: Sequence[EnergyRow]) -> Outcome:
    """The value of the user's ``equation`` (Ry), or why it cannot be computed."""
    name, expression = parse_equation(equation)
    if not expression and sum(row.energy_ry is not None for row in rows) < 2:
        return Outcome(name, None, _("São precisas pelo menos duas saídas com energia total"))
    try:
        text, values = substitute(expression, rows)
        return Outcome(name, evaluate(text, values))
    except ExpressionError as exc:
        return Outcome(name, None, str(exc))


def result_text(name: str, value_ry: float) -> str:
    """``E_ads = -0.12345678 Ry = -1.6797 eV``, with a decimal point."""
    return f"{name} = {value_ry:.8f} Ry = {value_ry * RY_TO_EV:.4f} eV"


# -- the report -------------------------------------------------------------------------------------
def report_text(rows: Sequence[EnergyRow], equation: str, outcome: Outcome) -> str:
    header = (_("Prefixo"), _("Arquivo"), _("Átomos"), _("Energia total (Ry)"))
    lines = [
        _("# Energia de adsorção"),
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for row in rows:
        atoms = "" if row.atoms is None else str(row.atoms)
        energy = f"{row.energy_ry:.8f}" if row.energy_ry is not None else f"— ({row.problem})"
        lines.append(f"| {row.name} | {row.path.name} | {atoms} | {energy} |")
    lines += ["", _("## Equação"), "", "```", equation.strip(), "```", ""]
    lines.append(_("**Resultado**: {text}").format(text=outcome.text))
    return "\n".join(lines) + "\n"


def report_name(rows: Sequence[EnergyRow]) -> str:
    """``energia_ads_<prefix1>_<prefix2>….md``, the prefixes in the table's order."""
    stems = (_UNSAFE.sub("_", row.prefix.strip()) or "pwscf" for row in rows)
    return (REPORT_PREFIX + "_".join(stems))[:NAME_LIMIT] + ".md"


def save_report(folder: Path, rows: Sequence[EnergyRow], equation: str, outcome: Outcome) -> Path:
    """Write the report into ``folder`` (worker); a name taken gets ``_2``, never overwritten."""
    text = report_text(rows, equation, outcome)
    return write_new(Path(folder) / report_name(rows), text, first=2)
