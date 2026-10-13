import itertools
import math

import numpy as np
import pytest
from helpers import make_structure

from viewer3d.core.measure import angle, dihedral, distance, nearest_image
from viewer3d.core.structure import AtomRef


def cubic(points, a=50.0):
    return make_structure(a * np.eye(3), np.asarray(points, float) / a, ["C"] * len(points))


R = [AtomRef(i) for i in range(4)]


def test_distance_value_and_delta():
    s = cubic([[0, 0, 0], [1, 2, 2]])
    d = distance(s, R[0], R[1])
    assert d.value == pytest.approx(3.0)
    assert d.delta == pytest.approx([1, 2, 2])


def test_distance_uses_the_exact_copy_and_is_lattice_invariant():
    s = cubic([[0, 0, 0], [1, 0, 0]], a=5.0)
    base = distance(s, R[0], R[1]).value
    assert distance(s, AtomRef(0, (3, -2, 1)), AtomRef(1, (3, -2, 1))).value == pytest.approx(base)
    far = distance(s, AtomRef(0), AtomRef(1, (1, 0, 0))).value  # not the minimum image
    assert far == pytest.approx(6.0)


@pytest.mark.parametrize(
    ("c", "expected"),
    [([1, 0, 0], 0.0), ([0, 1, 0], 90.0), ([-1, 0, 0], 180.0), ([1, 1, 0], 45.0)],
)
def test_angle_vertex_is_the_second_atom(c, expected):
    s = cubic([[1, 0, 0], [0, 0, 0], c])
    assert angle(s, R[0], R[1], R[2]) == pytest.approx(expected)


def test_angle_range_and_degenerate():
    rng = np.random.default_rng(3)
    for _ in range(50):
        s = cubic(rng.normal(size=(3, 3)) * 3)
        assert 0.0 <= angle(s, R[0], R[1], R[2]) <= 180.0
    s = cubic([[0, 0, 0], [0, 0, 0], [1, 0, 0]])
    assert math.isnan(angle(s, R[0], R[1], R[2]))


@pytest.mark.parametrize(
    ("d", "expected"),
    [([0, 1, 1], 90.0), ([0, -1, 1], -90.0), ([1, 0, 1], 0.0), ([-1, 0, 1], 180.0)],
)
def test_dihedral_known_values(d, expected):
    s = cubic([[1, 0, 0], [0, 0, 0], [0, 0, 1], d])
    assert dihedral(s, *R) == pytest.approx(expected)


def test_dihedral_sign_flips_with_reversal_and_is_rotation_invariant():
    rng = np.random.default_rng(5)
    pts = rng.normal(size=(4, 3)) * 2
    s = cubic(pts)
    forward = dihedral(s, *R)
    assert dihedral(s, R[3], R[2], R[1], R[0]) == pytest.approx(forward)  # reversal keeps sign
    mirrored = cubic(pts * np.array([1, 1, -1]))
    assert dihedral(mirrored, *R) == pytest.approx(-forward)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    rotated = cubic(pts @ q.T)
    assert dihedral(rotated, *R) == pytest.approx(forward)


def test_dihedral_is_independent_construction():
    # d obtained from a by rotating around the b->c axis by +phi counter... compare via geometry
    for phi in (-150.0, -30.0, 10.0, 77.0, 170.0):
        p = math.radians(phi)
        d = [math.cos(p), math.sin(p), 1.0]  # rear bond rotated by phi around +z
        s = cubic([[1, 0, 0], [0, 0, 0], [0, 0, 1], d])
        assert dihedral(s, *R) == pytest.approx(phi, abs=1e-9)


def test_nearest_image_in_oblique_cell_matches_brute_force():
    cell = np.array([[3.0, 0.0, 0.0], [2.8, 0.5, 0.0], [0.3, 0.4, 7.0]])  # very skewed
    rng = np.random.default_rng(11)
    frac = rng.uniform(-1, 2, size=(6, 3))
    s = make_structure(cell, frac, ["C"] * 6)
    for a in range(6):
        for b in range(6):
            ref_a = AtomRef(a, (1, -2, 0))
            got = nearest_image(s, ref_a, AtomRef(b))
            pos_a = s.position(ref_a)
            best = min(
                (np.linalg.norm(s.position(AtomRef(b, t)) - pos_a), t)
                for t in itertools.product(range(-8, 9), repeat=3)
            )
            assert np.linalg.norm(s.position(got) - pos_a) == pytest.approx(best[0])
