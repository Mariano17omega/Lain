"""Are the energies of the user's equation comparable? (spec 97 R3: item F6 of the 11/11/2026 report)

Only the outputs the equation uses count (a coefficient other than zero). They should share the
level of theory: cutoffs, functional (by its codes: pw.x names the same PBE several ways), dispersion
correction, pseudopotential of each element, occupations and spin; the complex and the substrate also
their cell, dipole correction (spec 98) and k-point mesh (the isolated molecule has a box of its
own on purpose). The atoms must balance element by element, Σ coefficient × count = 0, for any
equation linear in the energies.

Nothing here blocks the result: the warnings are shown and written into the report, and the notes
are what a reviewer asks (zero-point energy, dispersion, Γ for a molecule). A row without a level of
theory, or a value it lacks, stays out of that comparison: no warning for missing data.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

from ...i18n import _
from .adsorption_energy import EnergyRow, Role, calculate, parse_equation, substitute
from .expression import ExpressionError, evaluate
from .level_of_theory import MISSING, LevelOfTheory, cutoffs_text, occupations_text, spin_text

ZERO = 1e-12  # a smaller coefficient: the output is out of the equation
AFFINE = 1e-9  # relative tolerance of the test that the equation is affine
BALANCED = 1e-6  # atoms
SAME_CUTOFF = 1e-6  # Ry
SAME_CELL = 1e-3  # bohr: pw.x prints alat with 4 decimals and a(i) with 6


@dataclass(frozen=True)
class Consistency:
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def coefficients(expression: str, rows: Sequence[EnergyRow]) -> dict[str, float] | None:
    """The coefficient of each ``E(<name>)`` of ``expression`` (rows it does not name: absent), or
    None when it is not affine in the energies (a product or a quotient of them) or cannot be
    evaluated. ``f(0…0)``, then each energy at 1, then a check with all of them at ``i + 2``."""
    try:
        text, _values, internal = substitute(expression, rows)
        names = list(internal)

        def value(energies: Sequence[float]) -> float:
            return evaluate(text, {internal[n]: e for n, e in zip(names, energies, strict=True)})

        constant = value([0.0] * len(names))
        found = {
            name: value([float(i == j) for j in range(len(names))]) - constant
            for i, name in enumerate(names)
        }
        probe = [float(i + 2) for i in range(len(names))]
        expected = constant + sum(found[n] * x for n, x in zip(names, probe, strict=True))
        if not math.isclose(value(probe), expected, rel_tol=AFFINE, abs_tol=AFFINE):
            return None
    except ExpressionError:
        return None
    return found


def check(equation: str, rows: Sequence[EnergyRow]) -> Consistency:
    """The warnings and notes of ``equation`` over ``rows``; none while it has no value."""
    if calculate(equation, rows).value_ry is None:
        return Consistency()
    _name, expression = parse_equation(equation)
    found = coefficients(expression, rows)
    if found is None:
        named = substitute(expression, rows)[2]
        used = [row for row in rows if row.name in named]
    else:
        used = [row for row in rows if abs(found.get(row.name, 0.0)) >= ZERO]
    warnings = [_balance(used, found), *_same_theory(used), *_complex_and_substrate(used)]
    return Consistency(tuple(w for w in warnings if w), _notes(used))


# -- warnings ---------------------------------------------------------------------------------------
def _balance(used: Sequence[EnergyRow], found: dict[str, float] | None) -> str | None:
    if found is None:
        return _("A equação não é linear nas energias: o balanço de átomos não foi conferido.")
    sums: dict[str, float] = {}
    for row in used:
        if row.theory is None or not row.theory.composition:
            return None  # one output without its atoms: the balance cannot be told
        for element, count in row.theory.composition:
            sums[element] = sums.get(element, 0.0) + found[row.name] * count
    terms = [f"{element} {total:+g}" for element, total in sums.items() if abs(total) > BALANCED]
    if not terms:
        return None
    return _(
        "Os átomos não fecham: {terms}. O resultado é a energia de outra reação; com desprotonação, some a referência do H que falta (½ E(H₂), por exemplo). Uma referência numérica na equação (potencial químico) não entra nesta conta."
    ).format(terms=", ".join(terms))


def _same_theory(used: Sequence[EnergyRow]) -> list[str]:
    out: list[str] = []
    if groups := _groups(used, _cutoffs, cutoffs_text, _same_cutoffs):
        out.append(
            _(
                "Cutoffs diferentes (ecutwfc/ecutrho, Ry): {groups}. Só diferenças no mesmo cutoff cancelam o erro de base."
            ).format(groups=groups)
        )
    if groups := _groups(used, _functional, lambda t: t.xc_name or MISSING):
        out.append(_("Funcionais diferentes: {groups}.").format(groups=groups))
    if groups := _groups(
        used, lambda t: t.dispersion or "", lambda t: t.dispersion or _("nenhuma")
    ):
        out.append(_("Correção de dispersão diferente: {groups}.").format(groups=groups))
    for element in dict.fromkeys(el for row in used if row.theory for el, _f in row.theory.pseudos):
        if groups := _groups(used, _pseudos_of(element), _pseudos_text(element)):
            out.append(
                _("Pseudopotencial de {element} diferente: {groups}.").format(
                    element=element, groups=groups
                )
            )
    if groups := _groups(used, _occupations, occupations_text):
        out.append(
            _(
                'Ocupações diferentes: {groups}. Com smearing o "!" é a energia livre, e alargamentos diferentes não cancelam.'
            ).format(groups=groups)
        )
    if groups := _groups(used, lambda t: t.nspin, spin_text):
        out.append(
            _(
                "Spin diferente: {groups}. Confira se cada saída está no seu estado fundamental (a magnetização está no Resumo)."
            ).format(groups=groups)
        )
    return out


def _complex_and_substrate(used: Sequence[EnergyRow]) -> list[str]:
    """The cell, the dipole correction (spec 98) and the k-point mesh, between the complex and the
    substrate only. The irreducible k-points are not compared: the adsorbate breaks symmetries of
    the clean surface."""
    complex_ = next((row for row in used if row.role is Role.COMPLEX), None)
    substrate = next((row for row in used if row.role is Role.SUBSTRATE), None)
    if complex_ is None or substrate is None or complex_.theory is None or substrate.theory is None:
        return []
    out = []
    a, b = complex_.theory, substrate.theory
    if a.cell is not None and b.cell is not None and not _same_cell(a.cell, b.cell):
        out.append(
            _(
                "Células diferentes: complexo ({complex}) e substrato ({substrate}). O erro da amostragem só cancela na mesma célula."
            ).format(complex=complex_.name, substrate=substrate.name)
        )
    if a.dipole_correction != b.dipole_correction:
        with_, without = (complex_, substrate) if a.dipole_correction else (substrate, complex_)
        out.append(
            _(
                "Correção de dipolo em {with_} e não em {without}: complexo e substrato precisam da mesma escolha, ou a diferença de energia leva o termo do dipolo."
            ).format(with_=with_.name, without=without.name)
        )
    if a.k_mesh is not None and b.k_mesh is not None and a.k_mesh != b.k_mesh:
        out.append(
            _(
                "Malhas k diferentes: complexo ({complex}: {mesh}) e substrato ({substrate}: {mesh_2})."
            ).format(
                complex=complex_.name, mesh=a.k_mesh, substrate=substrate.name, mesh_2=b.k_mesh
            )
        )
    return out


def _groups(
    rows: Sequence[EnergyRow],
    key: Callable[[LevelOfTheory], Hashable | None],
    value: Callable[[LevelOfTheory], str],
    same: Callable[[Hashable, Hashable], bool] = operator.eq,
) -> str | None:
    """``"{value} ({names}); …"`` in the table's order when ``rows`` fall into two or more groups by
    ``key`` (a row whose key is None stays out); None otherwise. A group shows its first row's value."""
    groups: list[tuple[Hashable, str, list[str]]] = []
    for row in rows:
        if row.theory is None or (k := key(row.theory)) is None:
            continue
        group = next((g for g in groups if same(g[0], k)), None)
        if group is None:
            groups.append((k, value(row.theory), [row.name]))
        else:
            group[2].append(row.name)
    if len(groups) < 2:
        return None
    return "; ".join(f"{text} ({', '.join(names)})" for _k, text, names in groups)


def _cutoffs(theory: LevelOfTheory) -> tuple[float, float] | None:
    if theory.ecutwfc is None or theory.ecutrho is None:
        return None
    return (theory.ecutwfc, theory.ecutrho)


def _same_cutoffs(a: Hashable, b: Hashable) -> bool:
    assert isinstance(a, tuple) and isinstance(b, tuple)
    return all(
        math.isclose(x, y, rel_tol=0, abs_tol=SAME_CUTOFF) for x, y in zip(a, b, strict=True)
    )


def _functional(theory: LevelOfTheory) -> Hashable | None:
    if theory.xc_codes is not None:
        return theory.xc_codes
    return theory.xc_name.upper() if theory.xc_name else None


def _pseudos_of(element: str) -> Callable[[LevelOfTheory], frozenset[str] | None]:
    def key(theory: LevelOfTheory) -> frozenset[str] | None:
        return frozenset(name for el, name in theory.pseudos if el == element) or None

    return key


def _pseudos_text(element: str) -> Callable[[LevelOfTheory], str]:
    def text(theory: LevelOfTheory) -> str:
        return ", ".join(name for el, name in theory.pseudos if el == element)

    return text


def _occupations(theory: LevelOfTheory) -> Hashable | None:
    if theory.k_points is None and not theory.tetrahedra:
        return None  # no "number of k points" line: the occupations are not known
    return (theory.tetrahedra, theory.smearing, theory.degauss)


def _same_cell(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> bool:
    return all(
        math.isclose(x, y, rel_tol=0, abs_tol=SAME_CELL)
        for u, v in zip(a, b, strict=True)
        for x, y in zip(u, v, strict=True)
    )


# -- notes ------------------------------------------------------------------------------------------
def _notes(used: Sequence[EnergyRow]) -> tuple[str, ...]:
    notes = [_("Energia eletrônica: sem energia de ponto zero (ZPE) nem contribuição térmica.")]
    theories = [row.theory for row in used if row.theory is not None]
    if theories and not any(t.dispersion or t.nonlocal_functional for t in theories):
        notes.append(
            _(
                "Nenhuma das saídas usa correção de dispersão (vdw_corr) nem funcional vdW-DF: a fisissorção sai subestimada."
            )
        )
    for row in used:
        theory = row.theory
        if row.role is Role.ADSORBATE and theory is not None and (theory.k_points or 0) > 1:
            notes.append(
                _(
                    "{name}: {n} k-pontos irredutíveis. Uma molécula isolada numa caixa grande só precisa de Γ (K_POINTS gamma)."
                ).format(name=row.name, n=theory.k_points)
            )
    return tuple(notes)
