"""Direct lattice vectors from ``ibrav`` and ``celldm`` (port of QE 7.1 ``latgen``)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

BOHR = 0.529177210903  # Å per bohr
SR2 = 1.414213562373  # truncated on purpose: same constants as the QE source
SR3 = 1.732050807569

SUPPORTED_IBRAV = (0, 1, 2, 3, -3, 4, 5, -5, 6, 7, 8, 9, -9, 91, 10, 11, 12, -12, 13, -13, 14)


class LatticeError(ValueError):
    """Invalid lattice parameters; the message is in Portuguese and shown to the user."""


def celldm_from_abc(
    ibrav: int, a: float, b: float, c: float, cos_ab: float, cos_ac: float, cos_bc: float
) -> tuple[float, float, float, float, float, float]:
    """``A, B, C, cosAB, cosAC, cosBC`` (Å) -> ``celldm(1..6)`` (QE ``abc2celldm``)."""
    if a <= 0:
        raise LatticeError(f"parâmetro A deve ser positivo (valor: {a})")
    celldm = [a / BOHR, b / a, c / a, 0.0, 0.0, 0.0]
    if ibrav in (14, 0):
        celldm[3:] = [cos_bc, cos_ac, cos_ab]
    elif ibrav in (-12, -13):
        celldm[3:] = [0.0, cos_ac, 0.0]
    elif ibrav in (5, -5, 12, 13):
        celldm[3:] = [cos_ab, 0.0, 0.0]
    return tuple(celldm)  # type: ignore[return-value]


def _need(celldm: Sequence[float], ibrav: int, indices: Sequence[int]) -> None:
    for i in indices:
        if celldm[i - 1] <= 0:
            raise LatticeError(f"ibrav = {ibrav} exige celldm({i}) > 0 (valor: {celldm[i - 1]})")


def _check_cos(value: float, name: str, low: float = -1.0) -> None:
    if not (low < value < 1.0):
        raise LatticeError(f"{name} fora do intervalo permitido (valor: {value})")


def latgen(ibrav: int, celldm: Sequence[float]) -> np.ndarray:
    """Return the 3x3 matrix of lattice vectors (rows a1, a2, a3) in bohr."""
    if ibrav not in SUPPORTED_IBRAV or ibrav == 0:
        raise LatticeError(f"ibrav = {ibrav} não suportado")
    dm = [float(x) for x in celldm] + [0.0] * (6 - len(celldm))
    _need(dm, ibrav, [1])
    a = dm[0]
    c2, c3, c4, c5, c6 = dm[1], dm[2], dm[3], dm[4], dm[5]
    b, cc = a * c2, a * c3
    if ibrav in (4, 6, 7):
        _need(dm, ibrav, [3])
    if ibrav in (8, 9, -9, 91, 10, 11, 12, -12, 13, -13, 14):
        _need(dm, ibrav, [2, 3])

    if ibrav == 1:
        v = a * np.eye(3)
    elif ibrav == 2:
        v = a / 2 * np.array([[-1, 0, 1], [0, 1, 1], [-1, 1, 0]])
    elif ibrav == 3:
        v = a / 2 * np.array([[1, 1, 1], [-1, 1, 1], [-1, -1, 1]])
    elif ibrav == -3:
        v = a / 2 * np.array([[-1, 1, 1], [1, -1, 1], [1, 1, -1]])
    elif ibrav == 4:
        v = a * np.array([[1, 0, 0], [-0.5, SR3 / 2, 0], [0, 0, c3]])
    elif abs(ibrav) == 5:
        _check_cos(c4, "celldm(4) (cos γ)", -0.5)
        t1, t2 = math.sqrt(1 + 2 * c4), math.sqrt(1 - c4)
        if ibrav == 5:
            x, y, z = a * t2 / SR2, -a * t2 / SR2 / SR3, a * t1 / SR3
            v = np.array([[x, y, z], [0, SR2 * a * t2 / SR3, z], [-x, y, z]])
        else:
            u, w = a * (t1 - 2 * t2) / 3, a * (t1 + t2) / 3
            v = np.array([[u, w, w], [w, u, w], [w, w, u]])
    elif ibrav == 6:
        v = a * np.diag([1.0, 1.0, c3])
    elif ibrav == 7:
        v = a / 2 * np.array([[1, -1, c3], [1, 1, c3], [-1, -1, c3]])
    elif ibrav == 8:
        v = np.array([[a, 0, 0], [0, b, 0], [0, 0, cc]])
    elif ibrav == 9:
        v = np.array([[a / 2, b / 2, 0], [-a / 2, b / 2, 0], [0, 0, cc]])
    elif ibrav == -9:
        v = np.array([[a / 2, -b / 2, 0], [a / 2, b / 2, 0], [0, 0, cc]])
    elif ibrav == 91:
        v = np.array([[a, 0, 0], [0, b / 2, -cc / 2], [0, b / 2, cc / 2]])
    elif ibrav == 10:
        v = np.array([[a / 2, 0, cc / 2], [a / 2, b / 2, 0], [0, b / 2, cc / 2]])
    elif ibrav == 11:
        v = np.array([[a / 2, b / 2, cc / 2], [-a / 2, b / 2, cc / 2], [-a / 2, -b / 2, cc / 2]])
    elif ibrav in (12, -12, 13, -13):
        if ibrav > 0:
            cos = c4
            _check_cos(cos, "celldm(4) (cos γ)")
        else:
            cos = c5
            _check_cos(cos, "celldm(5) (cos β)")
        sin = math.sqrt(1 - cos**2)
        if ibrav == 12:
            v = np.array([[a, 0, 0], [b * cos, b * sin, 0], [0, 0, cc]])
        elif ibrav == -12:
            v = np.array([[a, 0, 0], [0, b, 0], [cc * cos, 0, cc * sin]])
        elif ibrav == 13:
            v = np.array([[a / 2, 0, -cc / 2], [b * cos, b * sin, 0], [a / 2, 0, cc / 2]])
        else:
            v = np.array([[a / 2, b / 2, 0], [-a / 2, b / 2, 0], [cc * cos, 0, cc * sin]])
    else:  # ibrav == 14
        _check_cos(c4, "celldm(4) (cos α)")
        _check_cos(c5, "celldm(5) (cos β)")
        _check_cos(c6, "celldm(6) (cos γ)")
        sg = math.sqrt(1 - c6**2)
        arg = (1 + 2 * c4 * c5 * c6 - c4**2 - c5**2 - c6**2) / (1 - c6**2)
        if arg <= 0:
            raise LatticeError("ângulos incompatíveis: a célula triclínica tem volume nulo")
        t = math.sqrt(arg)
        v = np.array([[a, 0, 0], [b * c6, b * sg, 0], [cc * c5, cc * (c4 - c5 * c6) / sg, cc * t]])

    v = np.asarray(v, dtype=float)
    if abs(np.linalg.det(v)) < 1e-10 * a**3:
        raise LatticeError("célula com volume nulo")
    return v
