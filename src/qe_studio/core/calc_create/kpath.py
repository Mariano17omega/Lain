"""K-points of the generated inputs (spec 25 R5): a band path as ``K_POINTS crystal_b`` and a manual
mesh as ``K_POINTS automatic``.

``suggest_path`` asks pymatgen for the high-symmetry path (Setyawan–Curtarolo) of the SCF's crystal
and writes it in fractions of the *input's* reciprocal vectors, the ones pw.x reads ``crystal_b`` in.
pymatgen standardizes the cell first, so its points are converted through the integer matrix that
takes its primitive cell to the input's (``Lattice.find_all_mappings``). pymatgen takes seconds to
import: ``suggest_path`` runs in workers only, and imports it inside.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..qe.lattice import Crystal

__all__ = [
    "DEFAULT_NPTS",
    "KMesh",
    "KPath",
    "KPathUnavailable",
    "KPoint",
    "suggest_path",
    "to_card",
]

DEFAULT_NPTS = 20
_LENGTH_TOLERANCE = 0.01  # fractional: pymatgen's standard cell is symmetrized (symprec 0.01 Å)
_ANGLE_TOLERANCE = 1.0  # degrees


class KPathUnavailable(Exception):
    """No suggested path (no pymatgen, no structure, odd cell): the user types the points."""


@dataclass(frozen=True)
class KMesh:
    """A Monkhorst–Pack mesh: ``n1 n2 n3`` and the shifts ``s1 s2 s3`` (0 or 1)."""

    n: tuple[int, int, int]
    shift: tuple[int, int, int] = (0, 0, 0)

    @property
    def count(self) -> int:
        return self.n[0] * self.n[1] * self.n[2]

    def problems(self) -> list[str]:
        out = []
        if min(self.n) < 1:
            out.append("a rede de k-points precisa de n1, n2, n3 ≥ 1")
        if any(s not in (0, 1) for s in self.shift):
            out.append("os deslocamentos da rede são 0 ou 1")
        return out

    def card(self) -> tuple[str, list[str]]:
        """Option and body of ``K_POINTS automatic``."""
        return "automatic", [" ".join(str(v) for v in (*self.n, *self.shift))]

    @classmethod
    def parse(cls, text: str) -> KMesh | None:
        """``8 8 8`` or ``8 8 8 0 0 0`` (the body line of an automatic card); None otherwise."""
        try:
            values = [int(token) for token in text.split()]
        except ValueError:
            return None
        if len(values) not in (3, 6):
            return None
        n = (values[0], values[1], values[2])
        shift = (values[3], values[4], values[5]) if len(values) == 6 else (0, 0, 0)
        return cls(n, shift)


@dataclass(frozen=True)
class KPoint:
    label: str  # as it goes in the card's comment ("Gamma", "X"); may be empty
    frac: tuple[float, float, float]  # in units of the input's reciprocal vectors
    npts: int = DEFAULT_NPTS  # points to the next one


@dataclass(frozen=True)
class KPath:
    points: tuple[KPoint, ...]
    # Index i: the path jumps from point i to i + 1 (``X|U``), so point i weighs 1.
    breaks: frozenset[int] = frozenset()
    warnings: tuple[str, ...] = ()

    def weights(self) -> list[int]:
        last = len(self.points) - 1
        return [
            1 if i == last or i in self.breaks else max(int(point.npts), 1)
            for i, point in enumerate(self.points)
        ]

    def problems(self) -> list[str]:
        if len(self.points) < 2:
            return ["Defina ao menos 2 pontos do caminho"]
        return []


def _coordinate(value: float) -> str:
    return f"{value + 0.0: .8f}"  # + 0.0: no "-0.00000000"


def to_card(path: KPath) -> tuple[str, list[str]]:
    """Option and body of ``K_POINTS crystal_b``: the count, then ``f1 f2 f3 weight ! label``."""
    rows = [str(len(path.points))]
    for point, weight in zip(path.points, path.weights(), strict=True):
        row = " ".join(_coordinate(v) for v in point.frac) + f" {weight:4d}"
        rows.append(f"{row}  ! {point.label}" if point.label.strip() else row)
    return "crystal_b", rows


def label_of(name: str) -> str:
    """pymatgen's label as written in the card: ``\\Gamma`` → ``Gamma``, ``\\Sigma_1`` →
    ``Sigma_1`` (the plot reads ``Gamma`` as Γ)."""
    return re.sub(r"\\", "", name).strip()


# -- the suggestion -----------------------------------------------------------------------------------
def _elements(labels: Sequence[str], is_valid) -> tuple[list[str], list[str]]:
    """The element of each species label (``Fe1`` → Fe, ``O2`` → O) and a warning when labels
    that differ (magnetic sites) become one element."""
    elements, by_element = [], {}
    for label in labels:
        letters = re.sub(r"[^A-Za-z]", "", label)
        element = next(
            (cand for cand in (letters[:2].capitalize(), letters[:1].upper()) if is_valid(cand)),
            None,
        )
        if element is None:
            raise KPathUnavailable(f"o rótulo {label} não é um elemento químico")
        elements.append(element)
        by_element.setdefault(element, set()).add(label)
    notes = [
        f"{', '.join(sorted(names))} tratados como {element}: o caminho segue a simetria "
        "cristalina, não a magnética"
        for element, names in by_element.items()
        if len(names) > 1
    ]
    return elements, notes


def _to_input_cell(prim_lattice, lattice) -> tuple[np.ndarray, list[str]]:
    """The integer matrix S with input = S · primitive (rows), the closest to the identity."""
    mappings = prim_lattice.find_all_mappings(
        lattice, ltol=_LENGTH_TOLERANCE, atol=_ANGLE_TOLERANCE, skip_rotation_matrix=True
    )
    scales = [np.rint(m[2]).astype(int) for m in mappings]
    if not scales:
        raise KPathUnavailable(
            "a célula do input não corresponde à célula padrão do pymatgen: digite o caminho"
        )
    scale = min(scales, key=lambda s: (np.abs(s - np.eye(3)).sum(), int((s < 0).sum())))
    notes = []
    folds = round(abs(np.linalg.det(scale)))
    if folds > 1:
        notes.append(
            f"a célula do input tem {folds}× o volume da primitiva: as bandas aparecem dobradas"
        )
    elif not np.array_equal(scale, np.eye(3, dtype=int)):
        notes.append("pontos convertidos da célula padrão do pymatgen para a célula do input")
    return scale, notes


def suggest_path(crystal: Crystal | None, npts: int = DEFAULT_NPTS) -> KPath:
    """The Setyawan–Curtarolo path of ``crystal`` in the input's reciprocal coordinates. Raises
    ``KPathUnavailable``. Workers only (imports pymatgen)."""
    if crystal is None:
        raise KPathUnavailable("a estrutura do SCF não pôde ser lida: digite os pontos do caminho")
    try:
        from pymatgen.core import Element, Lattice, Structure
        from pymatgen.symmetry.bandstructure import HighSymmKpath
    except ImportError as exc:
        raise KPathUnavailable("pymatgen não está instalado: digite os pontos do caminho") from exc

    species, notes = _elements(crystal.labels, Element.is_valid_symbol)
    structure = Structure(Lattice(crystal.cell), species, crystal.frac)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "input structure does not match the standard": handled
        try:
            kpath = HighSymmKpath(structure, path_type="setyawan_curtarolo")
        except Exception as exc:  # noqa: BLE001 - spglib and pymatgen raise assorted errors
            raise KPathUnavailable(f"o pymatgen não achou o caminho: {exc}") from exc
    if not kpath.kpath or not kpath.kpath.get("path"):
        raise KPathUnavailable("o pymatgen não achou o caminho desta rede")
    scale, mapping_notes = _to_input_cell(kpath.prim.lattice, structure.lattice)
    coordinates = kpath.kpath["kpoints"]
    points: list[KPoint] = []
    breaks: set[int] = set()
    for segment in kpath.kpath["path"]:
        if points:
            breaks.add(len(points) - 1)
        for name in segment:
            frac = scale @ np.asarray(coordinates[name], dtype=float)
            points.append(
                KPoint(label_of(name), (float(frac[0]), float(frac[1]), float(frac[2])), npts)
            )
    return KPath(tuple(points), frozenset(breaks), tuple(notes + mapping_notes))
