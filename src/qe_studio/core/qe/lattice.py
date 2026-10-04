"""The crystal a pw.x input describes: cell and fractional positions, without ASE (spec 25 R5).

ASE's ``read_espresso_in`` refuses ``ibrav != 0``, the way most inputs are written, so the cell is
built here with a port of Quantum ESPRESSO's ``latgen`` (``Modules/latgen.f90``, QE 7.1) and
``abc2celldm``. The vectors must be QE's own: ``K_POINTS crystal_b`` coordinates are in units of the
reciprocal vectors pw.x derives from them.

Only what a band path needs is read: the cell, the species label of each site and its fractional
position. Errors are ``StructureError`` with a Portuguese sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .input_edit import InputEditor
from .pw_input import fortran_float

__all__ = ["BOHR_ANGSTROM", "Crystal", "StructureError", "cell_vectors", "celldm_from_abc"]

BOHR_ANGSTROM = 0.529177210903  # QE's bohr_radius_angs (CODATA 2018)
_SR2 = 1.414213562373  # the constants latgen uses, digits included
_SR3 = 1.732050807569
IBRAVS = frozenset({0, 1, 2, 3, -3, 4, 5, -5, 6, 7, 8, 9, -9, 91, 10, 11, 12, -12, 13, -13, 14})


class StructureError(Exception):
    """Why the structure of an input cannot be read, in Portuguese."""


@dataclass(frozen=True)
class Crystal:
    cell: np.ndarray = field(repr=False)  # (3, 3), rows a1 a2 a3 in Å
    labels: tuple[str, ...]  # the ATOMIC_POSITIONS label of each site
    frac: np.ndarray = field(repr=False)  # (n, 3) fractional coordinates


def _require(ok: bool, what: str) -> None:
    if not ok:
        raise StructureError(f"{what} inválido para o ibrav")


def cell_vectors(ibrav: int, celldm: tuple[float, ...] | list[float]) -> np.ndarray:
    """Rows a1, a2, a3 in Bohr of a lattice with ``ibrav != 0`` (``latgen_lib``)."""
    c = [0.0] + [float(v) for v in (*celldm, 0, 0, 0, 0, 0, 0)][:6]  # 1-based like Fortran
    a = c[1]
    _require(a > 0, "celldm(1)")
    v = np.zeros((3, 3))
    if ibrav == 1:
        v[:] = np.eye(3) * a
    elif ibrav == 2:
        v[:] = a / 2 * np.array([[-1, 0, 1], [0, 1, 1], [-1, 1, 0]])
    elif ibrav == 3:
        v[:] = a / 2 * np.array([[1, 1, 1], [-1, 1, 1], [-1, -1, 1]])
    elif ibrav == -3:
        v[:] = a / 2 * np.array([[-1, 1, 1], [1, -1, 1], [1, 1, -1]])
    elif ibrav == 4:
        _require(c[3] > 0, "celldm(3)")
        v[:] = a * np.array([[1, 0, 0], [-0.5, _SR3 / 2, 0], [0, 0, c[3]]])
    elif abs(ibrav) == 5:
        _require(-0.5 < c[4] < 1.0, "celldm(4)")
        term1, term2 = np.sqrt(1 + 2 * c[4]), np.sqrt(1 - c[4])
        if ibrav == 5:
            x, y, z = a * term2 / _SR2, -a * term2 / _SR2 / _SR3, a * term1 / _SR3
            v[:] = [[x, y, z], [0, _SR2 * a * term2 / _SR3, z], [-x, y, z]]
        else:
            u, w = a * (term1 - 2 * term2) / 3, a * (term1 + term2) / 3
            v[:] = [[u, w, w], [w, u, w], [w, w, u]]
    elif ibrav == 6:
        _require(c[3] > 0, "celldm(3)")
        v[:] = a * np.diag([1, 1, c[3]])
    elif ibrav == 7:
        _require(c[3] > 0, "celldm(3)")
        v[:] = a / 2 * np.array([[1, -1, c[3]], [1, 1, c[3]], [-1, -1, c[3]]])
    elif ibrav in (8, 9, -9, 91, 10, 11):
        _require(c[2] > 0, "celldm(2)")
        _require(c[3] > 0, "celldm(3)")
        b, cc = a * c[2], a * c[3]
        v[:] = {
            8: [[a, 0, 0], [0, b, 0], [0, 0, cc]],
            9: [[a / 2, b / 2, 0], [-a / 2, b / 2, 0], [0, 0, cc]],
            -9: [[a / 2, -b / 2, 0], [a / 2, b / 2, 0], [0, 0, cc]],
            91: [[a, 0, 0], [0, b / 2, -cc / 2], [0, b / 2, cc / 2]],
            10: [[a / 2, 0, cc / 2], [a / 2, b / 2, 0], [0, b / 2, cc / 2]],
            11: [[a / 2, b / 2, cc / 2], [-a / 2, b / 2, cc / 2], [-a / 2, -b / 2, cc / 2]],
        }[ibrav]
    elif ibrav in (12, -12, 13, -13):
        _require(c[2] > 0, "celldm(2)")
        _require(c[3] > 0, "celldm(3)")
        cos = c[4] if ibrav > 0 else c[5]
        _require(abs(cos) < 1, "celldm(4)" if ibrav > 0 else "celldm(5)")
        sin, b, cc = np.sqrt(1 - cos**2), a * c[2], a * c[3]
        v[:] = {
            12: [[a, 0, 0], [b * cos, b * sin, 0], [0, 0, cc]],
            -12: [[a, 0, 0], [0, b, 0], [cc * cos, 0, cc * sin]],
            13: [[a / 2, 0, -cc / 2], [b * cos, b * sin, 0], [a / 2, 0, cc / 2]],
            -13: [[a / 2, b / 2, 0], [-a / 2, b / 2, 0], [cc * cos, 0, cc * sin]],
        }[ibrav]
    elif ibrav == 14:
        _require(c[2] > 0, "celldm(2)")
        _require(c[3] > 0, "celldm(3)")
        for i in (4, 5, 6):
            _require(abs(c[i]) < 1, f"celldm({i})")
        sin_g = np.sqrt(1 - c[6] ** 2)
        term = 1 + 2 * c[4] * c[5] * c[6] - c[4] ** 2 - c[5] ** 2 - c[6] ** 2
        _require(term >= 0, "conjunto de celldm")
        term = np.sqrt(term / (1 - c[6] ** 2))
        b, cc = a * c[2], a * c[3]
        v[:] = [
            [a, 0, 0],
            [b * c[6], b * sin_g, 0],
            [cc * c[5], cc * (c[4] - c[5] * c[6]) / sin_g, cc * term],
        ]
    else:
        raise StructureError(f"ibrav = {ibrav} não existe")
    return v


def celldm_from_abc(
    ibrav: int, a: float, b: float, c: float, cos_ab: float, cos_ac: float, cos_bc: float
) -> list[float]:
    """``celldm(1..6)`` from ``A`` (Å), ``B``, ``C``, ``cosAB``, ``cosAC``, ``cosBC`` (``abc2celldm``)."""
    if a <= 0:
        raise StructureError("A deve ser positivo")
    head = [a / BOHR_ANGSTROM, b / a, c / a]
    if ibrav in (14, 0):
        return [*head, cos_bc, cos_ac, cos_ab]
    if ibrav in (-12, -13):
        return [*head, 0.0, cos_ac, 0.0]
    if ibrav in (5, -5, 12, 13):
        return [*head, cos_ab, 0.0, 0.0]
    return [*head, 0.0, 0.0, 0.0]


# -- reading an input ------------------------------------------------------------------------------
def _number(editor: InputEditor, key: str) -> float | None:
    text = editor.get("system", key)
    return None if text is None else fortran_float(text)


def _celldm(editor: InputEditor, ibrav: int) -> list[float] | None:
    """celldm(1..6) as written, or from A, B, C…; None when neither is given."""
    celldm = [_number(editor, f"celldm({i})") for i in range(1, 7)]
    if any(value is not None for value in celldm):
        return [value or 0.0 for value in celldm]
    abc = {key: _number(editor, key) for key in ("a", "b", "c", "cosab", "cosac", "cosbc")}
    if abc["a"] is None:
        return None
    return celldm_from_abc(
        ibrav,
        abc["a"],
        abc["b"] or 0.0,
        abc["c"] or 0.0,
        abc["cosab"] or 0.0,
        abc["cosac"] or 0.0,
        abc["cosbc"] or 0.0,
    )


def _rows(lines: tuple[str, ...], count: int, what: str) -> list[list[float]]:
    rows = []
    for line in lines[:count]:
        values = [fortran_float(token) for token in line.split()[:3]]
        if len(values) < 3 or any(v is None for v in values):
            raise StructureError(f"linha de {what} ilegível: {line.strip()}")
        rows.append([float(v) for v in values if v is not None])
    if len(rows) < count:
        raise StructureError(f"{what} incompleto")
    return rows


def _cell_bohr(editor: InputEditor, ibrav: int) -> tuple[np.ndarray, float]:
    """The cell in Bohr and alat (Bohr), as pw.x sets them."""
    celldm = _celldm(editor, ibrav)
    if ibrav != 0:
        if celldm is None:
            raise StructureError("faltam celldm(1) ou A no &SYSTEM")
        return cell_vectors(ibrav, celldm), celldm[0]
    card = editor.card("CELL_PARAMETERS")
    if card is None:
        raise StructureError("ibrav = 0 sem CELL_PARAMETERS")
    rows = np.array(_rows(card.lines, 3, "CELL_PARAMETERS"))
    unit = card.option or "alat"
    if unit.startswith("alat"):
        if celldm is None or celldm[0] <= 0:
            raise StructureError("CELL_PARAMETERS alat sem celldm(1) ou A")
        return rows * celldm[0], celldm[0]
    if unit not in ("bohr", "angstrom"):
        raise StructureError(f"unidade de CELL_PARAMETERS desconhecida: {unit}")
    cell = rows if unit == "bohr" else rows / BOHR_ANGSTROM
    return cell, float(np.linalg.norm(cell[0]))


def crystal_from_editor(editor: InputEditor) -> Crystal:
    """The crystal of a pw.x input read by ``editor``. Raises ``StructureError``."""
    ibrav_text = editor.get("system", "ibrav")
    ibrav_value = fortran_float(ibrav_text) if ibrav_text is not None else None
    if ibrav_value is None or ibrav_value != int(ibrav_value) or int(ibrav_value) not in IBRAVS:
        raise StructureError(f"ibrav ausente ou inválido ({ibrav_text})")
    ibrav = int(ibrav_value)
    cell, alat = _cell_bohr(editor, ibrav)
    if abs(np.linalg.det(cell)) < 1e-8:
        raise StructureError("célula de volume nulo")
    card = editor.card("ATOMIC_POSITIONS")
    if card is None or not card.lines:
        raise StructureError("sem ATOMIC_POSITIONS")
    unit = card.option or "alat"
    if unit not in ("crystal", "alat", "bohr", "angstrom"):
        raise StructureError(f"ATOMIC_POSITIONS {unit} não é suportado")
    nat_value = _number(editor, "nat")
    nat = int(nat_value) if nat_value is not None else len(card.lines)
    if len(card.lines) < nat:
        raise StructureError(f"nat = {nat}, mas ATOMIC_POSITIONS tem {len(card.lines)} linhas")
    labels, coords = [], []
    for line in card.lines[:nat]:
        tokens = line.split()
        values = [fortran_float(token) for token in tokens[1:4]]
        if len(tokens) < 4 or any(v is None for v in values):
            raise StructureError(f"linha de ATOMIC_POSITIONS ilegível: {line.strip()}")
        labels.append(tokens[0])
        coords.append([float(v) for v in values if v is not None])
    positions = np.array(coords)
    if unit == "crystal":
        frac = positions
    else:
        scale = {"alat": alat, "bohr": 1.0, "angstrom": 1 / BOHR_ANGSTROM}[unit]
        frac = positions * scale @ np.linalg.inv(cell)
    return Crystal(cell * BOHR_ANGSTROM, tuple(labels), frac)
