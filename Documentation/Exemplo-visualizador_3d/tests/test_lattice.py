import math

import numpy as np
import pytest

from viewer3d.core.lattice import BOHR, LatticeError, celldm_from_abc, latgen

A, B_RATIO, C_RATIO = 7.0, 1.3, 1.7
COS = 0.2  # generic angle cosine, never 0 or 90 degrees


def _cos(u, v):
    return float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)))


def _volume(v):
    return abs(float(np.linalg.det(v)))


def _sin(c):
    return math.sqrt(1 - c * c)


b, cc = A * B_RATIO, A * C_RATIO
# ibrav, celldm, expected primitive-cell volume (closed form)
VOLUMES = [
    (1, [A], A**3),
    (2, [A], A**3 / 4),
    (3, [A], A**3 / 2),
    (-3, [A], A**3 / 2),
    (4, [A, 0, C_RATIO], A**3 * math.sqrt(3) / 2 * C_RATIO),
    (5, [A, 0, 0, COS], A**3 * math.sqrt(1 - 3 * COS**2 + 2 * COS**3)),
    (-5, [A, 0, 0, COS], A**3 * math.sqrt(1 - 3 * COS**2 + 2 * COS**3)),
    (6, [A, 0, C_RATIO], A**3 * C_RATIO),
    (7, [A, 0, C_RATIO], A**3 * C_RATIO / 2),
    (8, [A, B_RATIO, C_RATIO], A * b * cc),
    (9, [A, B_RATIO, C_RATIO], A * b * cc / 2),
    (-9, [A, B_RATIO, C_RATIO], A * b * cc / 2),
    (91, [A, B_RATIO, C_RATIO], A * b * cc / 2),
    (10, [A, B_RATIO, C_RATIO], A * b * cc / 4),
    (11, [A, B_RATIO, C_RATIO], A * b * cc / 2),
    (12, [A, B_RATIO, C_RATIO, COS], A * b * cc * _sin(COS)),
    (-12, [A, B_RATIO, C_RATIO, 0, COS], A * b * cc * _sin(COS)),
    (13, [A, B_RATIO, C_RATIO, COS], A * b * cc * _sin(COS) / 2),
    (-13, [A, B_RATIO, C_RATIO, 0, COS], A * b * cc * _sin(COS) / 2),
    (
        14,
        [A, B_RATIO, C_RATIO, 0.1, 0.2, 0.3],
        A * b * cc * math.sqrt(1 - 0.1**2 - 0.2**2 - 0.3**2 + 2 * 0.1 * 0.2 * 0.3),
    ),
]


@pytest.mark.parametrize(("ibrav", "celldm", "volume"), VOLUMES)
def test_volume_matches_closed_form(ibrav, celldm, volume):
    v = latgen(ibrav, celldm)
    assert v.shape == (3, 3)
    assert _volume(v) == pytest.approx(volume, rel=1e-6)


def test_cubic_families_lengths_and_angles():
    v = latgen(1, [A])
    assert np.allclose(v, A * np.eye(3))
    fcc = latgen(2, [A])
    assert np.allclose(np.linalg.norm(fcc, axis=1), A / math.sqrt(2))
    for i, j in ((0, 1), (0, 2), (1, 2)):
        assert _cos(fcc[i], fcc[j]) == pytest.approx(0.5, abs=1e-9)  # 60 degrees
    bcc = latgen(3, [A])
    assert np.allclose(np.linalg.norm(bcc, axis=1), A * math.sqrt(3) / 2)


def test_hexagonal_angle_is_120():
    v = latgen(4, [A, 0, C_RATIO])
    assert np.linalg.norm(v[0]) == pytest.approx(A, rel=1e-9)
    assert np.linalg.norm(v[2]) == pytest.approx(A * C_RATIO, rel=1e-9)
    assert _cos(v[0], v[1]) == pytest.approx(-0.5, abs=1e-9)
    assert _cos(v[0], v[2]) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("ibrav", [5, -5])
def test_rhombohedral_equal_lengths_and_cos(ibrav):
    v = latgen(ibrav, [A, 0, 0, COS])
    assert np.allclose(np.linalg.norm(v, axis=1), A, rtol=1e-8)
    for i, j in ((0, 1), (0, 2), (1, 2)):
        assert _cos(v[i], v[j]) == pytest.approx(COS, abs=1e-8)


def test_monoclinic_and_triclinic_lengths_and_angles():
    v = latgen(12, [A, B_RATIO, C_RATIO, COS])
    assert np.allclose(np.linalg.norm(v, axis=1), [A, b, cc])
    assert _cos(v[0], v[1]) == pytest.approx(COS)
    v = latgen(-12, [A, B_RATIO, C_RATIO, 0, COS])
    assert _cos(v[0], v[2]) == pytest.approx(COS)
    v = latgen(14, [A, B_RATIO, C_RATIO, 0.1, 0.2, 0.3])
    assert np.allclose(np.linalg.norm(v, axis=1), [A, b, cc])
    assert _cos(v[1], v[2]) == pytest.approx(0.1)  # cos(bc) = celldm(4)
    assert _cos(v[0], v[2]) == pytest.approx(0.2)  # cos(ac) = celldm(5)
    assert _cos(v[0], v[1]) == pytest.approx(0.3)  # cos(ab) = celldm(6)


def test_abc_conversion_roundtrip():
    celldm = celldm_from_abc(14, 5.0, 6.0, 7.0, 0.3, 0.2, 0.1)
    assert celldm == pytest.approx((5.0 / BOHR, 1.2, 1.4, 0.1, 0.2, 0.3))
    v = latgen(14, celldm) * BOHR
    assert np.linalg.norm(v, axis=1) == pytest.approx([5.0, 6.0, 7.0])
    assert celldm_from_abc(12, 5, 6, 7, 0.3, 0.2, 0.1)[3:] == (0.3, 0.0, 0.0)
    assert celldm_from_abc(-12, 5, 6, 7, 0.3, 0.2, 0.1)[3:] == (0.0, 0.2, 0.0)
    assert celldm_from_abc(1, 5, 6, 7, 0.3, 0.2, 0.1)[3:] == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("ibrav", "celldm"),
    [
        (99, [A]),
        (1, [0.0]),
        (1, [-3.0]),
        (8, [A, 0.0, 1.0]),
        (5, [A, 0, 0, 1.0]),
        (5, [A, 0, 0, -0.5]),
        (12, [A, 1, 1, 1.0]),
        (14, [A, 1, 1, 0.0, 0.0, 1.0]),
        (14, [A, 1, 1, 0.9, 0.9, -0.9]),
    ],
)
def test_invalid_parameters_raise_lattice_error(ibrav, celldm):
    with pytest.raises(LatticeError):
        latgen(ibrav, celldm)
