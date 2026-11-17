"""The level of theory of a pw.x output (spec 97 R2): what makes two total energies comparable.

The header gives it through the Summary's ``Scanner`` (cutoffs, the functional's name and codes, the
dispersion correction, the pseudopotentials, the occupations, the cell and the site list); the spin
comes from the parsed output and the k-point mesh from the input of the same name, as in the Summary.
The ``*_text`` functions are what the adsorption window and its report show, ``"—"`` when the output
does not say.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...i18n import _, ngettext
from ..calc_create.surface import SurfaceError
from ..calc_create.surface.elements import element_of
from ..qe.pw_output import PwOutput
from ..qe.summary.scan import Facts
from ..qe.units import number

MISSING = "—"

Vector = tuple[float, float, float]


@dataclass(frozen=True)
class LevelOfTheory:
    ecutwfc: float | None = None  # Ry
    ecutrho: float | None = None
    xc_name: str | None = None  # as pw.x prints it, spaces collapsed: "SLA PW PBE PBE"
    xc_codes: tuple[int, ...] | None = None  # iexch icorr igcx igcc inlc imeta imetac
    dispersion: str | None = None  # "DFT-D3", "MBD"… (Scanner)
    pseudos: tuple[tuple[str, str], ...] = ()  # (element, file), sorted
    smearing: str | None = None  # the name pw.x prints: "Gaussian", "Marzari-Vanderbilt"
    degauss: float | None = None  # Ry
    tetrahedra: bool = False
    nspin: int | None = None  # 1, 2, or 4 when noncollinear, as QE
    magnetization: float | None = None  # total, Bohr mag/cell
    k_points: int | None = None  # irreducible
    k_mesh: str | None = None  # of the input: "automatic 8×8×8 (0 0 0)"
    cell: tuple[Vector, Vector, Vector] | None = None  # bohr: alat × a(i)
    composition: tuple[tuple[str, int], ...] = ()  # (element, count) in the site list's order
    dipole_correction: bool = False  # tefield + dipfield (Scanner, spec 98)

    @property
    def nonlocal_functional(self) -> bool:
        """A vdW-DF functional: ``inlc`` (the fifth code) is not zero."""
        codes = self.xc_codes
        return codes is not None and len(codes) > 4 and codes[4] != 0


def element(label: str) -> str:
    """The element of a species label (``Fe1`` → ``Fe``); the label itself when it has none."""
    try:
        return element_of(label)
    except SurfaceError:
        return label


def level_of_theory(facts: Facts, pw: PwOutput | None, mesh: str | None) -> LevelOfTheory:
    """``pw``: ``sniff(path).pw`` (None: no spin); ``mesh``: ``k_mesh_of(path)``."""
    kpoints = facts.hit("kpoints", first=True)
    k_points = smearing = degauss = None
    if kpoints is not None:
        count, name, width = kpoints.groups
        k_points = int(count) if count else None
        if name:
            smearing = name.removesuffix(" smearing").strip()
            degauss = _float(width)
    xc = _group(facts, "xc")
    composition: dict[str, int] = {}
    for label, count in facts.species.items():
        key = element(label)
        composition[key] = composition.get(key, 0) + count
    nspin = None
    if pw is not None:
        nspin = 4 if pw.noncollinear else 2 if pw.spin_polarized else 1
    return LevelOfTheory(
        ecutwfc=_float(_group(facts, "ecutwfc")),
        ecutrho=_float(_group(facts, "ecutrho")),
        xc_name=" ".join(xc.split()) if xc else None,
        xc_codes=facts.xc_codes,
        dispersion=facts.dispersion,
        pseudos=tuple(sorted({(element(el), name) for el, name, _at in facts.pseudos.values()})),
        smearing=smearing,
        degauss=degauss,
        tetrahedra=facts.tetrahedra,
        nspin=nspin,
        magnetization=pw.total_magnetization if pw is not None else None,
        k_points=k_points,
        k_mesh=mesh,
        cell=_cell(facts),
        composition=tuple(composition.items()),
        dipole_correction=facts.dipole_correction,
    )


def _group(facts: Facts, key: str) -> str | None:
    hit = facts.hit(key, first=True)
    return hit.groups[0] if hit else None


def _float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return number(text)
    except ValueError:
        return None


def _cell(facts: Facts) -> tuple[Vector, Vector, Vector] | None:
    alat = _float(_group(facts, "alat"))
    if alat is None or len(facts.axes) != 3:
        return None
    a1, a2, a3 = facts.axes
    return (_scaled(a1, alat), _scaled(a2, alat), _scaled(a3, alat))


def _scaled(axis: Vector, alat: float) -> Vector:
    return (alat * axis[0], alat * axis[1], alat * axis[2])


# -- texts ------------------------------------------------------------------------------------------
def cutoffs_text(theory: LevelOfTheory | None) -> str:
    """``25/118.918`` (ecutwfc/ecutrho, Ry)."""
    if theory is None or (theory.ecutwfc is None and theory.ecutrho is None):
        return MISSING
    return "/".join(MISSING if v is None else f"{v:g}" for v in (theory.ecutwfc, theory.ecutrho))


def xc_text(theory: LevelOfTheory | None) -> str:
    """``SLA PW PBX PBC + DFT-D3 (3 corpos)``."""
    if theory is None:
        return MISSING
    name = theory.xc_name or MISSING
    return f"{name} + {theory.dispersion}" if theory.dispersion else name


def occupations_text(theory: LevelOfTheory | None) -> str:
    """``smearing Gaussian, 0.0100 Ry``, ``tetrahedra`` or "sem smearing" (pw.x's header does not tell
    ``fixed`` from ``from_input``)."""
    if theory is None:
        return MISSING
    if theory.tetrahedra:
        return "tetrahedra"
    if theory.smearing:
        width = MISSING if theory.degauss is None else f"{theory.degauss:.4f}"
        return f"smearing {theory.smearing}, {width} Ry"
    return MISSING if theory.k_points is None else _("sem smearing")


def spin_text(theory: LevelOfTheory | None) -> str:
    """The Summary's words (``summary/build.py:_spin``), with the magnetization when collinear."""
    if theory is None or theory.nspin is None:
        return MISSING
    if theory.nspin == 4:
        return _("não colinear")
    if theory.nspin == 1:
        return _("não polarizado")
    text = _("colinear (nspin=2)")
    if theory.magnetization is not None:
        text += f", {theory.magnetization:.2f} μB"
    return text


def mesh_text(theory: LevelOfTheory | None) -> str:
    """The input's mesh, else the irreducible k-points the output counts."""
    if theory is None:
        return MISSING
    if theory.k_mesh:
        return theory.k_mesh
    if theory.k_points is None:
        return MISSING
    n = theory.k_points
    return ngettext("{n} k-ponto", "{n} k-pontos", n).format(n=n)


def k_points_tip(theory: LevelOfTheory | None) -> str:
    """``29 k-pontos irredutíveis``; empty when the output does not say."""
    if theory is None or theory.k_points is None:
        return ""
    n = theory.k_points
    return ngettext("{n} k-ponto irredutível", "{n} k-pontos irredutíveis", n).format(n=n)


def pseudos_tip(theory: LevelOfTheory | None) -> str:
    """``Pseudopotenciais:`` and an ``<element>: <file>`` line each; empty without them."""
    if theory is None or not theory.pseudos:
        return ""
    return "\n".join([_("Pseudopotenciais:"), *(f"{el}: {name}" for el, name in theory.pseudos)])
