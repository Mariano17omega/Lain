import itertools

import numpy as np
import pytest
from helpers import make_structure

from viewer3d.core import bonds as bonds_module
from viewer3d.core.bonds import BondGraph, bonds_for, compute_bonds, covalent_radii
from viewer3d.core.structure import AtomRef


def pair_keys(bonds):
    """Orientation-independent identity of every bond: {(i, j, s), (j, i, -s)}."""
    return {
        frozenset(
            {
                (int(i), int(j), tuple(int(x) for x in s)),
                (int(j), int(i), tuple(int(-x) for x in s)),
            }
        )
        for i, j, s in zip(bonds.i, bonds.j, bonds.shift, strict=True)
    }


def brute_force(structure, factor=1.15, reach=4):
    r = covalent_radii(structure)
    out = set()
    cart_frac = structure.frac
    for s in itertools.product(range(-reach, reach + 1), repeat=3):
        s = np.array(s)
        for i in range(len(structure)):
            for j in range(len(structure)):
                d = np.linalg.norm((cart_frac[j] + s - cart_frac[i]) @ structure.cell)
                if 0.1 < d < factor * (r[i] + r[j]):
                    t = tuple(int(x) for x in s)
                    out.add(frozenset({(i, j, t), (j, i, tuple(-x for x in t))}))
    return out


def test_silicon_has_four_neighbours(si):
    bonds = bonds_for(si)
    graph = BondGraph(bonds, len(si))
    assert len(bonds) == 4
    for index in range(2):
        near = graph.neighbors(AtomRef(index))
        assert len(near) == 4 == graph.coordination(AtomRef(index))
        assert all(d == pytest.approx(2.3372, abs=1e-3) for _, d in near)
    assert np.allclose(bonds.dist, 2.3372, atol=1e-3)


def test_h3chg_bonds(h3chg):
    bonds = bonds_for(h3chg)
    found = {
        (int(i), int(j)): float(d) for i, j, d in zip(bonds.i, bonds.j, bonds.dist, strict=True)
    }
    assert found[(0, 1)] == pytest.approx(2.316, abs=2e-3)  # Hg-C
    for h in (2, 3, 4):
        assert found[(1, h)] == pytest.approx(1.09, abs=1e-3)  # C-H
    assert len(found) == 4  # no Hg-H bond
    assert all((0, h) not in found for h in (2, 3, 4))


def test_kaolinite_coordination(kaolinite):
    bonds = bonds_for(kaolinite)
    graph = BondGraph(bonds, len(kaolinite))
    symbols = kaolinite.symbols
    coordination = {sym: set() for sym in set(symbols)}
    for index, sym in enumerate(symbols):
        coordination[sym].add(graph.coordination(AtomRef(index)))
    assert coordination["Si"] == {4}
    assert coordination["Al"] == {6}
    hg = symbols.index("Hg")
    carbon = symbols.index("C")
    near = {ref.index: d for ref, d in graph.neighbors(AtomRef(hg))}
    assert carbon in near and near[carbon] == pytest.approx(2.065, abs=0.01)
    others = [i for i in near if i != carbon]
    assert [symbols[i] for i in others] == ["O"]  # methylmercury sits on a surface oxygen
    assert near[others[0]] == pytest.approx(2.03, abs=0.02)
    assert graph.coordination(AtomRef(carbon)) == 4


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_matches_brute_force_on_oblique_cell_with_outside_atoms(seed):
    rng = np.random.default_rng(seed)
    cell = np.array([[4.0, 0.0, 0.0], [1.7, 3.5, 0.0], [-1.9, 1.1, 3.8]])
    n = 9
    frac = rng.uniform(-0.6, 1.6, size=(n, 3))
    s = make_structure(cell, frac, ["C"] * 5 + ["O"] * 2 + ["H"] * 2)
    assert pair_keys(bonds_for(s)) == brute_force(s)


def test_tree_and_dense_paths_agree(monkeypatch):
    rng = np.random.default_rng(7)
    cell = np.array([[6.0, 0.0, 0.0], [1.0, 5.5, 0.0], [0.5, -1.2, 6.5]])
    frac = rng.uniform(-0.3, 1.3, size=(120, 3))
    s = make_structure(cell, frac, ["C"] * 120)
    monkeypatch.setattr(bonds_module, "KDTREE_THRESHOLD", 10**9)
    dense = bonds_for(s)
    monkeypatch.setattr(bonds_module, "KDTREE_THRESHOLD", 0)
    tree = bonds_for(s)
    assert len(dense) > 20
    assert pair_keys(dense) == pair_keys(tree)


def test_tiny_cell_needs_more_than_one_image():
    s = make_structure(0.5 * np.eye(3), [[0.0, 0.0, 0.0]], ["C"])
    assert pair_keys(bonds_for(s)) == brute_force(s, reach=3)
    # |s|^2 <= 12 (limit 1.15 * 2 * 0.76 = 1.75 Å = 3.5 cells): 178 vectors, 89 bonds
    assert len(bonds_for(s)) == 89


def test_self_bond_is_listed_once():
    s = make_structure(1.3 * np.eye(3), [[0.0, 0.0, 0.0]], ["C"])
    bonds = bonds_for(s)
    assert len(bonds) == 3  # +a, +b, +c
    assert np.all(bonds.i == bonds.j)


def test_bond_set_is_invariant_to_wrapping_atoms(kaolinite):
    wrapped = make_structure(
        kaolinite.cell, kaolinite.frac - np.floor(kaolinite.frac), list(kaolinite.labels)
    )
    a = np.sort(bonds_for(kaolinite).dist)
    b = np.sort(bonds_for(wrapped).dist)
    assert a == pytest.approx(b)


def test_factor_changes_bond_count(si):
    assert len(bonds_for(si, factor=0.5)) == 0
    assert len(bonds_for(si, factor=1.15)) == 4
    assert len(bonds_for(si, factor=1.9)) > 4  # second neighbours at 3.82 Å


def test_neighbours_translate_with_the_copy(si):
    graph = BondGraph(bonds_for(si), len(si))
    base = graph.neighbors(AtomRef(0))
    moved = graph.neighbors(AtomRef(0, (2, -1, 3)))
    for (a, da), (b, db) in zip(base, moved, strict=True):
        assert b.index == a.index
        assert db == pytest.approx(da)
        assert b.shift == (a.shift[0] + 2, a.shift[1] - 1, a.shift[2] + 3)


def test_neighbour_relation_is_symmetric(kaolinite):
    graph = BondGraph(bonds_for(kaolinite), len(kaolinite))
    for index in range(len(kaolinite)):
        ref = AtomRef(index)
        for other, d in graph.neighbors(ref):
            back = {(r.index, r.shift): dd for r, dd in graph.neighbors(other)}
            assert back[(ref.index, ref.shift)] == pytest.approx(d)


def test_empty_structure_has_no_bonds():
    out = compute_bonds(np.eye(3), np.zeros((0, 3)), np.zeros(0))
    assert len(out) == 0
