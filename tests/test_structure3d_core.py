"""Spec 43 R1: the core of the proof of concept, ported (bonds, replicate, camera, pick, elements), on the
fixtures of Lain."""

import itertools

import numpy as np
import pytest

from qe_studio.core.calc_create.surface import SurfaceError
from qe_studio.core.calc_create.surface.elements import element_of
from qe_studio.core.structure3d import bonds as bonds_module
from qe_studio.core.structure3d.bonds import BondGraph, bonds_for, compute_bonds, covalent_radii
from qe_studio.core.structure3d.camera import Camera, frame_from
from qe_studio.core.structure3d.elements import element_for_label, symbol_from_label
from qe_studio.core.structure3d.model import AtomRef
from qe_studio.core.structure3d.pick import hit_test, pick
from qe_studio.core.structure3d.replicate import build_scene, original_mask, shifts
from qe_studio.core.structure3d.source import read_structure
from structure3d_helpers import BULK, MOLECULE, PW_INPUTS, SLAB_2X1, make_structure, si

VIEW = (800.0, 600.0)
SI_BOND = np.sqrt(3) / 4 * 10.16863713 * 0.529177210903  # √3/4 · celldm(1): 2.33 Å


@pytest.fixture(scope="module")
def bulk():
    return read_structure(BULK)


@pytest.fixture(scope="module")
def molecule():
    return read_structure(MOLECULE)


# -- elements ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "symbol"),
    [
        ("Fe1", "Fe"),
        ("Fe_up", "Fe"),
        ("C2", "C"),
        ("H_ads", "H"),
        ("Hg", "Hg"),
        ("O", "O"),
        ("si", "Si"),
        ("Cl", "Cl"),
        ("Ha", "H"),  # no element "Ha": the first letter
    ],
)
def test_label_rule(label, symbol):
    assert symbol_from_label(label) == symbol
    assert element_for_label(label).known


@pytest.mark.parametrize("label", ["X", "1Fe", "", "_", "Xx9"])
def test_unknown_labels_never_raise(label):
    info = element_for_label(label)  # "X" is Z = 0 in ASE and counts as unknown
    assert not info.known and info.z == 0
    assert info.color == (0.5, 0.5, 0.5)
    assert info.r_cov == info.r_vdw == 1.0


def test_known_element_data():
    hg = element_for_label("Hg")
    assert (hg.symbol, hg.z, hg.name) == ("Hg", 80, "Mercúrio")
    assert hg.r_cov == pytest.approx(1.32)
    assert element_for_label("H").r_cov == pytest.approx(0.31)
    for label in ("Pm", "Og", "Es"):  # no van der Waals radius in ASE
        assert element_for_label(label).r_vdw > 0


def _labels() -> set[str]:
    labels = {"Fe1", "Fe_up", "C2", "H_ads", "si", "Ha", "X", "1Fe", "Xx9", "_"}
    for path in PW_INPUTS:
        structure = read_structure(path)
        labels |= set(structure.labels) | {s.label for s in structure.species}
    return labels


@pytest.mark.parametrize("label", sorted(_labels()))
def test_the_label_rule_is_the_surface_one(label):
    try:
        expected = element_of(label)
    except SurfaceError:
        expected = None
    assert symbol_from_label(label) == expected


# -- bonds ---------------------------------------------------------------------------------------


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
    for s in itertools.product(range(-reach, reach + 1), repeat=3):
        s = np.array(s)
        for i in range(len(structure)):
            for j in range(len(structure)):
                d = np.linalg.norm((structure.frac[j] + s - structure.frac[i]) @ structure.cell)
                if 0.1 < d < factor * (r[i] + r[j]):
                    t = tuple(int(x) for x in s)
                    out.add(frozenset({(i, j, t), (j, i, tuple(-x for x in t))}))
    return out


def test_silicon_has_four_neighbours_at_a_quarter_of_the_diagonal():
    structure = si()
    bonds = bonds_for(structure)
    graph = BondGraph(bonds, len(structure))
    assert len(bonds) == 4
    for index in range(2):
        near = graph.neighbors(AtomRef(index))
        assert len(near) == 4 == graph.coordination(AtomRef(index))
        assert all(d == pytest.approx(SI_BOND) for _, d in near)
    assert pytest.approx(2.33, abs=0.01) == SI_BOND


def test_methylmercury_bonds(molecule):
    bonds = bonds_for(molecule)
    symbols = molecule.symbols
    found = {
        (symbols[i], symbols[j]): float(d)
        for i, j, d in zip(bonds.i, bonds.j, bonds.dist, strict=True)
    }
    pairs = [(symbols[i], symbols[j]) for i, j in zip(bonds.i, bonds.j, strict=True)]
    assert sorted(pairs) == [("C", "H")] * 3 + [("Hg", "C")]
    assert found[("Hg", "C")] == pytest.approx(2.316, abs=2e-3)
    assert np.all(bonds.shift == 0)  # a molecule in a big box: no periodic bond


def test_kaolinite_coordination(bulk):
    graph = BondGraph(bonds_for(bulk), len(bulk))
    coordination: dict[str, set[int]] = {}
    for index, symbol in enumerate(bulk.symbols):
        coordination.setdefault(symbol, set()).add(graph.coordination(AtomRef(index)))
    assert coordination["Si"] == {4}
    assert coordination["Al"] == {6}
    assert coordination["H"] == {1}


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_matches_brute_force_on_oblique_cell_with_outside_atoms(seed):
    rng = np.random.default_rng(seed)
    cell = np.array([[4.0, 0.0, 0.0], [1.7, 3.5, 0.0], [-1.9, 1.1, 3.8]])
    frac = rng.uniform(-0.6, 1.6, size=(9, 3))
    structure = make_structure(cell, frac, ["C"] * 5 + ["O"] * 2 + ["H"] * 2)
    assert pair_keys(bonds_for(structure)) == brute_force(structure)


def test_tree_and_dense_paths_agree(monkeypatch):
    rng = np.random.default_rng(7)
    cell = np.array([[6.0, 0.0, 0.0], [1.0, 5.5, 0.0], [0.5, -1.2, 6.5]])
    structure = make_structure(cell, rng.uniform(-0.3, 1.3, size=(120, 3)), ["C"] * 120)
    monkeypatch.setattr(bonds_module, "KDTREE_THRESHOLD", 10**9)
    dense = bonds_for(structure)
    monkeypatch.setattr(bonds_module, "KDTREE_THRESHOLD", 0)
    tree = bonds_for(structure)
    assert len(dense) > 20
    assert pair_keys(dense) == pair_keys(tree)


def test_tiny_cell_needs_more_than_one_image():
    structure = make_structure(0.5 * np.eye(3), [[0.0, 0.0, 0.0]], ["C"])
    assert pair_keys(bonds_for(structure)) == brute_force(structure, reach=3)
    assert len(bonds_for(structure)) == 89  # |s|² ≤ 12 cells: 178 vectors, 89 bonds


def test_self_bond_is_listed_once():
    bonds = bonds_for(make_structure(1.3 * np.eye(3), [[0.0, 0.0, 0.0]], ["C"]))
    assert len(bonds) == 3  # +a, +b, +c
    assert np.all(bonds.i == bonds.j)


def test_bond_set_is_invariant_to_wrapping_atoms():
    slab = read_structure(SLAB_2X1)
    wrapped = make_structure(slab.cell, slab.frac - np.floor(slab.frac), list(slab.labels))
    assert np.sort(bonds_for(slab).dist) == pytest.approx(np.sort(bonds_for(wrapped).dist))


def test_factor_changes_bond_count():
    structure = si()
    assert len(bonds_for(structure, factor=0.5)) == 0
    assert len(bonds_for(structure, factor=1.15)) == 4
    assert len(bonds_for(structure, factor=1.9)) > 4  # second neighbours at 3.84 Å


def test_neighbours_translate_with_the_copy():
    structure = si()
    graph = BondGraph(bonds_for(structure), len(structure))
    base = graph.neighbors(AtomRef(0))
    moved = graph.neighbors(AtomRef(0, (2, -1, 3)))
    for (a, da), (b, db) in zip(base, moved, strict=True):
        assert b.index == a.index and db == pytest.approx(da)
        assert b.shift == (a.shift[0] + 2, a.shift[1] - 1, a.shift[2] + 3)


def test_neighbour_relation_is_symmetric(bulk):
    graph = BondGraph(bonds_for(bulk), len(bulk))
    for index in range(len(bulk)):
        ref = AtomRef(index)
        for other, d in graph.neighbors(ref):
            back = {(r.index, r.shift): dd for r, dd in graph.neighbors(other)}
            assert back[(ref.index, ref.shift)] == pytest.approx(d)


def test_empty_structure_has_no_bonds():
    assert len(compute_bonds(np.eye(3), np.zeros((0, 3)), np.zeros(0))) == 0


# -- replicate -----------------------------------------------------------------------------------


def segments_of_scene(scene):
    out = set()
    for a, b in zip(scene.bond_a, scene.bond_b, strict=True):
        pa, pb = scene.positions[a], scene.positions[b]
        out.add(frozenset({tuple(np.round(pa, 5)), tuple(np.round(pb, 5))}))
    return out


def expected_segments(structure, reps):
    """Recompute bonds on the explicit supercell and expand the periodic ones into segments."""
    copies = shifts(*reps)
    frac = np.vstack([(structure.frac + c) / np.array(reps) for c in copies])
    big = make_structure(
        structure.cell * np.array(reps)[:, None], frac, list(structure.labels) * len(copies)
    )
    bonds, cart = bonds_for(big), big.cart
    out = set()
    for i, j, s in zip(bonds.i, bonds.j, bonds.shift, strict=True):
        pj = cart[j] + s @ big.cell
        out.add(frozenset({tuple(np.round(cart[i], 5)), tuple(np.round(pj, 5))}))
        if np.any(s):  # the same bond seen from the partner inside the block
            pi = cart[i] - s @ big.cell
            out.add(frozenset({tuple(np.round(cart[j], 5)), tuple(np.round(pi, 5))}))
    return out


def test_shifts_order_and_original_mask():
    copies = shifts(2, 1, 3)
    assert copies.shape == (6, 3)
    assert copies[0].tolist() == [0, 0, 0] and copies[1].tolist() == [0, 0, 1]
    assert copies[-1].tolist() == [1, 0, 2]
    mask = original_mask(copies)
    assert mask.sum() == 1 and mask[0]


@pytest.mark.parametrize("reps", [(1, 1, 1), (2, 1, 1), (2, 2, 1), (1, 3, 2)])
def test_translation_matches_recompute_on_supercell(reps):
    structure = si()
    scene = build_scene(structure, bonds_for(structure), reps)
    assert scene.n_real == 2 * int(np.prod(reps))
    assert segments_of_scene(scene) == expected_segments(structure, reps)


def test_translation_matches_recompute_for_oblique_slab(bulk):
    scene = build_scene(bulk, bonds_for(bulk), (2, 1, 1))
    assert segments_of_scene(scene) == expected_segments(bulk, (2, 1, 1))


def test_atom_count_doubles_and_refs_are_exact():
    structure = si()
    one = build_scene(structure, bonds_for(structure), (1, 1, 1))
    two = build_scene(structure, bonds_for(structure), (2, 1, 1))
    assert two.n_real == 2 * one.n_real
    assert two.refs[0].shift == (0, 0, 0) and two.refs[2].shift == (1, 0, 0)
    assert two.original.sum() == one.n_real
    for k in range(4):
        assert np.allclose(two.positions[k], structure.position(two.refs[k]))


def test_ghosts_are_unique_outside_the_block_and_not_real():
    structure = si()
    scene = build_scene(structure, bonds_for(structure), (1, 1, 1))
    assert scene.n_ghost > 0
    ghosts = np.round(scene.positions[scene.n_real :], 5)
    assert len(np.unique(ghosts, axis=0)) == len(ghosts)
    real = np.round(scene.positions[: scene.n_real], 5)
    assert not any((g == real).all(axis=1).any() for g in ghosts)
    assert (np.stack([scene.bond_a, scene.bond_b]) < scene.n_real).any(axis=0).all()


def test_molecule_has_no_ghosts(molecule):
    scene = build_scene(molecule, bonds_for(molecule), (1, 1, 1))
    assert scene.n_ghost == 0 and len(scene.bond_a) == 4


def test_bounds_points_include_block_corners():
    structure = si()
    scene = build_scene(structure, bonds_for(structure), (2, 1, 1))
    assert len(scene.bounds_points()) == 8 + len(scene.positions)
    assert np.allclose(scene.block[0], 2 * structure.cell[0])


# -- camera --------------------------------------------------------------------------------------


def random_rotation(seed):
    q, _ = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def test_orthographic_projection_preserves_ratios_and_parallels():
    cam = Camera()
    cam.perspective, cam.rotation, cam.zoom = False, random_rotation(1), 17.0
    p = np.array([[0, 0, 0], [1, 2, 3], [3, 6, 9], [1, 0, 0], [2, 2, 3]], dtype=float)
    xy, depth, scale = cam.project(p, VIEW)
    assert np.allclose(scale, 1.0)
    assert np.allclose(xy[2] - xy[0], 3 * (xy[1] - xy[0]))
    assert np.allclose(xy[4] - xy[3], xy[1] - xy[0])
    assert depth[2] - depth[0] == pytest.approx(3 * (depth[1] - depth[0]))


def test_perspective_scale_is_f_over_f_plus_depth():
    cam = Camera()
    cam.focal = 40.0
    _xy, depth, scale = cam.project(np.array([[0, 0, 0], [0, 0, -10.0], [0, 0, 10.0]]), VIEW)
    assert depth.tolist() == [0.0, 10.0, -10.0]  # the viewer is on +z
    assert scale == pytest.approx(40.0 / (40.0 + depth))
    assert scale[2] > 1.0 > scale[1]


def test_point_behind_the_eye_is_not_drawn():
    cam = Camera()
    cam.focal = 5.0
    xy, _, scale = cam.project(np.array([[0, 0, 20.0]]), VIEW)
    assert np.isnan(xy).all() and np.isnan(scale).all()


def test_center_maps_to_viewport_centre_and_y_points_up():
    cam = Camera()
    cam.center = np.array([1.0, 2.0, 3.0])
    xy, _, _ = cam.project(np.array([[1.0, 2.0, 3.0], [1.0, 3.0, 3.0]]), VIEW)
    assert xy[0] == pytest.approx([400.0, 300.0])
    assert xy[1][1] < xy[0][1]


def test_arcball_keeps_a_rotation_and_is_reversible():
    cam = Camera()
    start = cam.rotation.copy()
    cam.arcball_begin(400, 300, VIEW)
    cam.arcball_drag(520, 340, VIEW)
    r = cam.rotation
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-12) and np.linalg.det(r) == pytest.approx(1)
    assert not np.allclose(r, start)
    cam.arcball_drag(400, 300, VIEW)
    assert np.allclose(cam.rotation, start, atol=1e-12)


def test_zoom_keeps_point_under_cursor():
    cam = Camera()
    cam.perspective, cam.rotation, cam.pan = False, random_rotation(4), np.array([13.0, -7.0])
    cursor = (250.0, 410.0)
    v = np.array(
        [(cursor[0] - 400 - cam.pan[0]) / cam.zoom, -(cursor[1] - 300 - cam.pan[1]) / cam.zoom, 0]
    )
    world = cam.center + cam.rotation.T @ v
    cam.zoom_at(1.7, cursor, VIEW)
    xy, _, _ = cam.project(world[None, :], VIEW)
    assert xy[0] == pytest.approx(cursor)


def test_fit_frames_all_points():
    cam = Camera()
    pts = np.random.default_rng(2).uniform(-5, 20, size=(40, 3))
    cam.perspective = False
    cam.reset(pts, VIEW, center=pts.mean(axis=0))
    xy, _, _ = cam.project(pts, VIEW)
    assert xy[:, 0].min() >= 0 and xy[:, 0].max() <= VIEW[0]
    assert xy[:, 1].min() >= 0 and xy[:, 1].max() <= VIEW[1]
    span = max(np.ptp(xy[:, 0]) / VIEW[0], np.ptp(xy[:, 1]) / VIEW[1])
    assert span == pytest.approx(0.9, abs=1e-6)


def test_isometric_view_has_z_up_and_collapses_the_diagonal():
    cam = Camera()
    cam.perspective = False
    cam.set_isometric()
    xy, depth, _ = cam.project(np.array([[0, 0, 0], [1, 1, 1], [0, 0, 1.0]]), VIEW)
    assert xy[1] == pytest.approx(xy[0]) and depth[1] < depth[0] and xy[2][1] < xy[0][1]


def test_view_along_lattice_and_cartesian_axes():
    cell = np.array([[4.0, 0, 0], [1.0, 5.0, 0], [0.5, 0.7, 6.0]])
    cam = Camera()
    cam.perspective = False
    for name, k in (("a", 0), ("b", 1), ("c", 2)):
        cam.view_axis(name, cell)
        xy, depth, _ = cam.project(np.array([[0, 0, 0.0], cell[k]]), VIEW)
        assert xy[1] == pytest.approx(xy[0], abs=1e-9) and depth[1] < depth[0]
    cam.view_axis("z", np.eye(3))
    xy, _, _ = cam.project(np.array([[0, 0, 0.0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]), VIEW)
    assert xy[1][0] > xy[0][0] and xy[2][1] < xy[0][1] and xy[3] == pytest.approx(xy[0])


def test_frame_from_handles_parallel_up():
    r = frame_from(np.array([0, 0, 1.0]), np.array([0, 0, 2.0]))
    assert np.allclose(r @ r.T, np.eye(3)) and np.linalg.det(r) == pytest.approx(1.0)


def turned(axis: str, degrees: float) -> np.ndarray:
    """The right-hand rotation matrix about a world axis, written out (not the camera's code)."""
    t = np.radians(degrees)
    c, s = np.cos(t), np.sin(t)
    return {
        "x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
        "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
        "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]),
    }[axis]


def isometric_camera() -> Camera:
    cam = Camera()
    cam.center = np.array([1.0, -2.0, 0.5])
    cam.set_isometric()
    cam.zoom, cam.pan, cam.focal = 33.0, np.array([12.0, -7.0]), 17.0
    return cam


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_a_step_and_its_opposite_cancel_and_eight_steps_close_the_turn(axis):
    cam = isometric_camera()
    start = cam.rotation.copy()
    cam.rotate_world(axis, 45.0)
    assert not np.allclose(cam.rotation, start)
    cam.rotate_world(axis, -45.0)
    assert np.allclose(cam.rotation, start, atol=1e-12)
    for _ in range(8):
        cam.rotate_world(axis, 45.0)
    assert np.allclose(cam.rotation, start, atol=1e-12)
    assert np.allclose(cam.rotation @ cam.rotation.T, np.eye(3), atol=1e-12)


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_rotate_world_turns_the_structure_about_the_axis_through_the_center(axis):
    cam = isometric_camera()
    points = np.array([[2.0, 0.3, -1.0], [0.0, 0.0, 0.0], [-1.5, 2.5, 3.0], cam.center])
    before = cam.camera_coords(points)
    camera_before = Camera()
    camera_before.rotation, camera_before.center = cam.rotation.copy(), cam.center.copy()
    cam.rotate_world(axis, 90.0)
    # what the view shows afterwards is the old view of the points turned +90° about the axis
    turned_points = (points - cam.center) @ turned(axis, 90.0).T + cam.center
    assert np.allclose(cam.camera_coords(points), camera_before.camera_coords(turned_points))
    assert np.allclose(cam.camera_coords(cam.center), 0.0)  # the center stays where it was
    assert not np.allclose(cam.camera_coords(points), before)


def test_rotate_world_right_hand_rule_and_the_rest_of_the_view_stays():
    cam = Camera()  # identity: the camera frame is the world's
    cam.rotate_world("z", 90.0)
    # +x of the structure now points where +y was: the camera sees (0, 1, 0)
    assert np.allclose(
        cam.camera_coords(np.array([[1.0, 0.0, 0.0]])), [[0.0, 1.0, 0.0]], atol=1e-12
    )
    cam.rotate_world("x", 90.0)  # x+ takes +y to +z
    assert np.allclose(
        cam.camera_coords(np.array([[0.0, 1.0, 0.0]])),
        turned("z", 90.0) @ turned("x", 90.0) @ [0.0, 1.0, 0.0],
        atol=1e-12,
    )

    cam = isometric_camera()
    kept = (cam.zoom, cam.pan.copy(), cam.center.copy(), cam.focal)
    cam.rotate_world("y", 45.0)
    assert (cam.zoom, cam.focal) == (kept[0], kept[3])
    assert np.array_equal(cam.pan, kept[1]) and np.array_equal(cam.center, kept[2])


def test_rotate_world_refuses_an_unknown_axis():
    cam = Camera()
    before = cam.rotation.copy()
    for axis in ("a", "w", "", "X"):
        with pytest.raises(ValueError):
            cam.rotate_world(axis, 45.0)
    assert np.array_equal(cam.rotation, before)


# -- pick ----------------------------------------------------------------------------------------


def test_pick_chooses_front_atom_of_an_overlap():
    xy = np.array([[100.0, 100.0], [102.0, 101.0], [300.0, 300.0]])
    radii = np.array([10.0, 10.0, 10.0])
    order = np.argsort(np.array([5.0, 1.0, 0.0]))  # atom 1 is nearer than atom 0
    refs = [AtomRef(0), AtomRef(1), AtomRef(2)]
    assert pick((101.0, 100.0), xy, radii, order, refs) == AtomRef(1)
    assert pick((88.0, 100.0), xy, radii, order, refs) == AtomRef(0)
    assert pick((200.0, 200.0), xy, radii, order, refs) is None


def test_pick_tolerance_and_nan():
    xy = np.array([[50.0, 50.0], [np.nan, np.nan]])
    radii = np.array([10.0, 10.0])
    order = np.array([0, 1])
    assert hit_test((62.5, 50.0), xy, radii, order) == 0  # radius + 3 px
    assert hit_test((63.5, 50.0), xy, radii, order) is None
    assert hit_test((50.0, 50.0), xy[1:], radii[1:], np.array([0])) is None
    assert hit_test((0, 0), xy, radii, np.array([], dtype=int)) is None
