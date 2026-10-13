import numpy as np
import pytest
from helpers import make_structure

from viewer3d.core.bonds import bonds_for
from viewer3d.core.replicate import build_scene, original_mask, shifts


def segments_of_scene(scene):
    out = set()
    for a, b in zip(scene.bond_a, scene.bond_b, strict=True):
        pa, pb = scene.positions[a], scene.positions[b]
        out.add(frozenset({tuple(np.round(pa, 5)), tuple(np.round(pb, 5))}))
    return out


def expected_segments(structure, reps):
    """Recompute bonds on the explicit supercell and expand the periodic ones into segments."""
    r1, r2, r3 = reps
    copies = shifts(r1, r2, r3)
    frac = np.vstack([(structure.frac + c) / np.array(reps) for c in copies])
    labels = list(structure.labels) * len(copies)
    big = make_structure(structure.cell * np.array(reps)[:, None], frac, labels)
    bonds = bonds_for(big)
    cart = big.cart
    out = set()
    for i, j, s in zip(bonds.i, bonds.j, bonds.shift, strict=True):
        pj = cart[j] + s @ big.cell
        out.add(frozenset({tuple(np.round(cart[i], 5)), tuple(np.round(pj, 5))}))
        if np.any(s):  # the same bond seen from the partner inside the block
            pi = cart[i] - s @ big.cell
            out.add(frozenset({tuple(np.round(cart[j], 5)), tuple(np.round(pi, 5))}))
    return out


def test_shifts_order_and_original_mask():
    s = shifts(2, 1, 3)
    assert s.shape == (6, 3)
    assert s[0].tolist() == [0, 0, 0]
    assert s[1].tolist() == [0, 0, 1]
    assert s[-1].tolist() == [1, 0, 2]
    mask = original_mask(s)
    assert mask.sum() == 1 and mask[0]


@pytest.mark.parametrize("reps", [(1, 1, 1), (2, 1, 1), (2, 2, 1), (1, 3, 2)])
def test_translation_matches_recompute_on_supercell(si, reps):
    scene = build_scene(si, bonds_for(si), reps)
    assert scene.n_real == 2 * int(np.prod(reps))
    assert segments_of_scene(scene) == expected_segments(si, reps)


def test_translation_matches_recompute_for_oblique_slab(kaolinite):
    reps = (2, 1, 1)
    scene = build_scene(kaolinite, bonds_for(kaolinite), reps)
    assert segments_of_scene(scene) == expected_segments(kaolinite, reps)


def test_atom_count_doubles_and_refs_are_exact(si):
    one = build_scene(si, bonds_for(si), (1, 1, 1))
    two = build_scene(si, bonds_for(si), (2, 1, 1))
    assert two.n_real == 2 * one.n_real
    assert two.refs[0].shift == (0, 0, 0) and two.refs[2].shift == (1, 0, 0)
    assert two.original.sum() == one.n_real
    for k in (0, 1, 2, 3):
        ref = two.refs[k]
        assert np.allclose(two.positions[k], si.position(ref))


def test_ghosts_are_unique_outside_the_block_and_not_real(si):
    scene = build_scene(si, bonds_for(si), (1, 1, 1))
    assert scene.n_ghost > 0
    ghosts = np.round(scene.positions[scene.n_real :], 5)
    assert len(np.unique(ghosts, axis=0)) == len(ghosts)
    real = np.round(scene.positions[: scene.n_real], 5)
    assert not any((g == real).all(axis=1).any() for g in ghosts)
    # every bond has at least one real end; ghosts only ever appear as one end
    ends = np.stack([scene.bond_a, scene.bond_b])
    assert (ends < scene.n_real).any(axis=0).all()


def test_bond_lengths_in_scene_respect_threshold(kaolinite):
    scene = build_scene(kaolinite, bonds_for(kaolinite), (2, 2, 1))
    length = np.linalg.norm(scene.positions[scene.bond_a] - scene.positions[scene.bond_b], axis=1)
    assert length.max() < 2.6
    assert length.min() > 0.9


def test_molecule_has_no_ghosts(h3chg):
    scene = build_scene(h3chg, bonds_for(h3chg), (1, 1, 1))
    assert scene.n_ghost == 0
    assert len(scene.bond_a) == 4


def test_bounds_points_include_block_corners(si):
    scene = build_scene(si, bonds_for(si), (2, 1, 1))
    pts = scene.bounds_points()
    assert len(pts) == 8 + len(scene.positions)  # corners, real atoms and ghosts
    assert np.allclose(scene.block[0], 2 * si.cell[0])
