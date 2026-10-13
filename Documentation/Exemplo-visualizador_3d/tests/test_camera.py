import numpy as np
import pytest

from viewer3d.core.camera import Camera, frame_from
from viewer3d.core.pick import hit_test, pick
from viewer3d.core.structure import AtomRef

VIEW = (800.0, 600.0)


def random_rotation(seed):
    q, _ = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def test_orthographic_projection_preserves_ratios_and_parallels():
    cam = Camera()
    cam.perspective = False
    cam.rotation = random_rotation(1)
    cam.zoom = 17.0
    p = np.array([[0, 0, 0], [1, 2, 3], [3, 6, 9], [1, 0, 0], [2, 2, 3]], dtype=float)
    xy, depth, scale = cam.project(p, VIEW)
    assert np.allclose(scale, 1.0)
    # (p2 - p0) = 3 (p1 - p0)
    assert np.allclose(xy[2] - xy[0], 3 * (xy[1] - xy[0]))
    # (p4 - p3) is parallel and equal to (p1 - p0)
    assert np.allclose(xy[4] - xy[3], xy[1] - xy[0])
    assert depth[2] - depth[0] == pytest.approx(3 * (depth[1] - depth[0]))


def test_perspective_scale_is_f_over_f_plus_depth():
    cam = Camera()
    cam.focal = 40.0
    xy, depth, scale = cam.project(np.array([[0, 0, 0], [0, 0, -10.0], [0, 0, 10.0]]), VIEW)
    # identity rotation: viewer on +z, so z=-10 is farther away
    assert depth.tolist() == [0.0, 10.0, -10.0]
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
    assert xy[1][1] < xy[0][1]  # +y world is up the screen (smaller pixel y)


def test_arcball_keeps_a_rotation_and_is_reversible():
    cam = Camera()
    start = cam.rotation.copy()
    cam.arcball_begin(400, 300, VIEW)
    cam.arcball_drag(520, 340, VIEW)
    r = cam.rotation
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(r) == pytest.approx(1.0)
    assert not np.allclose(r, start)
    cam.arcball_drag(400, 300, VIEW)
    assert np.allclose(cam.rotation, start, atol=1e-12)


def test_arcball_horizontal_drag_turns_the_front_towards_the_cursor():
    cam = Camera()
    cam.perspective = False
    cam.arcball_begin(400, 300, VIEW)
    cam.arcball_drag(500, 300, VIEW)
    # a point on the front (+z toward viewer) of the sphere follows the cursor to the right
    xy, _, _ = cam.project(np.array([[0, 0, 5.0]]), VIEW)
    assert xy[0][0] > 400.0


def test_zoom_keeps_point_under_cursor():
    cam = Camera()
    cam.perspective = False
    cam.rotation = random_rotation(4)
    cam.pan = np.array([13.0, -7.0])
    cursor = (250.0, 410.0)
    # world point currently under the cursor (on the focal plane)
    v = np.array(
        [(cursor[0] - 400 - cam.pan[0]) / cam.zoom, -(cursor[1] - 300 - cam.pan[1]) / cam.zoom, 0]
    )
    world = cam.center + cam.rotation.T @ v
    cam.zoom_at(1.7, cursor, VIEW)
    xy, _, _ = cam.project(world[None, :], VIEW)
    assert xy[0] == pytest.approx(cursor)


def test_fit_frames_all_points():
    cam = Camera()
    rng = np.random.default_rng(2)
    pts = rng.uniform(-5, 20, size=(40, 3))
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
    assert xy[1] == pytest.approx(xy[0])  # looking down (1,1,1)
    assert depth[1] < depth[0]  # +diagonal is towards the viewer
    assert xy[2][1] < xy[0][1]  # +z is up


def test_view_along_lattice_vectors():
    cell = np.array([[4.0, 0, 0], [1.0, 5.0, 0], [0.5, 0.7, 6.0]])
    cam = Camera()
    cam.perspective = False
    for name, k in (("a", 0), ("b", 1), ("c", 2)):
        cam.view_axis(name, cell)
        xy, depth, _ = cam.project(np.array([[0, 0, 0.0], cell[k]]), VIEW)
        assert xy[1] == pytest.approx(xy[0], abs=1e-9)  # the axis points at the viewer
        assert depth[1] < depth[0]
    cam.view_axis("c", cell)
    xy, _, _ = cam.project(np.array([[0, 0, 0.0], cell[0]]), VIEW)
    assert xy[1][0] > xy[0][0]  # looking along c: a goes to the right


def test_cartesian_views():
    cam = Camera()
    cam.perspective = False
    cam.view_axis("z", np.eye(3))
    xy, depth, _ = cam.project(np.array([[0, 0, 0.0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]), VIEW)
    assert xy[1][0] > xy[0][0] and xy[2][1] < xy[0][1] and xy[3] == pytest.approx(xy[0])


def test_frame_from_handles_parallel_up():
    r = frame_from(np.array([0, 0, 1.0]), np.array([0, 0, 2.0]))
    assert np.allclose(r @ r.T, np.eye(3)) and np.linalg.det(r) == pytest.approx(1.0)


# ------------------------------------------------------------------------------ pick


def test_pick_chooses_front_atom_of_an_overlap():
    xy = np.array([[100.0, 100.0], [102.0, 101.0], [300.0, 300.0]])
    radii = np.array([10.0, 10.0, 10.0])
    depth = np.array([5.0, 1.0, 0.0])  # atom 1 is nearer the camera than atom 0
    order = np.argsort(depth)
    refs = [AtomRef(0), AtomRef(1), AtomRef(2)]
    assert pick((101.0, 100.0), xy, radii, order, refs) == AtomRef(1)
    assert pick((88.0, 100.0), xy, radii, order, refs) == AtomRef(0)  # only atom 0 covers it
    assert pick((200.0, 200.0), xy, radii, order, refs) is None


def test_pick_tolerance_and_nan():
    xy = np.array([[50.0, 50.0], [np.nan, np.nan]])
    radii = np.array([10.0, 10.0])
    order = np.array([0, 1])
    assert hit_test((50.0 + 12.5, 50.0), xy, radii, order) == 0  # radius + 3 px
    assert hit_test((50.0 + 13.5, 50.0), xy, radii, order) is None
    assert hit_test((50.0, 50.0), xy[1:], radii[1:], np.array([0])) is None
    assert hit_test((0, 0), xy, radii, np.array([], dtype=int)) is None
