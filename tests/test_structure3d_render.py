"""Spec 43 R2: the bonds are cylinders that start on the spheres' surface (``render_image``); spec 46 R2:
the two axis systems, their widths and the size of the labels."""

import numpy as np
import pytest
from PyQt6.QtCore import QSize

from qe_studio.core.structure3d.bonds import bonds_for
from qe_studio.core.structure3d.geometry import (
    BOND_RADIUS,
    STICK_RADIUS,
    half_bonds,
    species_radii,
)
from qe_studio.core.structure3d.model import AtomRef
from qe_studio.core.structure3d.options import STYLES, DisplayOptions
from qe_studio.core.structure3d.replicate import build_scene
from qe_studio.ui.widgets.structure3d.bonds_paint import half_quads
from qe_studio.ui.widgets.structure3d.canvas import StructureCanvas
from qe_studio.ui.widgets.structure3d.overlay import MIN_PICK_RADIUS
from qe_studio.ui.widgets.structure3d.renderer import (
    BACKGROUND,
    FIXED_GAP_PX,
    FIXED_RING,
    FIXED_WIDTH,
    GHOST_OPACITY,
)
from structure3d_helpers import make_structure, si, structure_of_text, water

SIZE = QSize(400, 300)
ZOOM = 120.0  # px per Å


def pixels(image) -> np.ndarray:
    """(h, w, 3) RGB of a premultiplied ARGB32 image (memory order B, G, R, A)."""
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    bgra = np.frombuffer(ptr, dtype=np.uint8).reshape(image.height(), image.width(), 4)
    return bgra[:, :, 2::-1].astype(int).copy()


def luminance(rgb) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def drawn_radii(structure, scene, style="bola-vareta", scale=1.0):
    from qe_studio.core.structure3d.elements import element_for_label

    elements = [element_for_label(s.label) for s in structure.species]
    r_cov = np.array([e.r_cov for e in elements])
    r_vdw = np.array([e.r_vdw for e in elements])
    return species_radii(style, r_cov, r_vdw, scale)[scene.species]


@pytest.fixture
def view(qapp):
    """The water molecule seen along z, orthographic, centered on the O, 120 px/Å."""
    from qe_studio.ui.theme.manager import ThemeManager

    canvas = StructureCanvas(ThemeManager("dark"), water())
    canvas.options.perspective = False
    canvas.options.show_cell = canvas.options.show_abc = canvas.options.show_xyz = False
    canvas.render_image(SIZE)  # first frame
    canvas.camera.view_axis("z", np.eye(3))
    canvas.camera.center = canvas.structure.position(AtomRef(0))
    canvas.camera.zoom, canvas.camera.pan = ZOOM, np.zeros(2)
    return canvas


# -- geometry ------------------------------------------------------------------------------------


def test_each_half_starts_on_its_sphere_along_the_axis():
    structure = water()
    scene = build_scene(structure, bonds_for(structure), (1, 1, 1))
    radii = drawn_radii(structure, scene)
    rho = BOND_RADIUS["bola-vareta"]
    halves = half_bonds(scene, radii, rho)
    assert len(halves) == 4  # two bonds, two halves each
    for owner, start, end in zip(halves.owner, halves.start, halves.end, strict=True):
        center = scene.positions[owner]
        cut = np.sqrt(radii[owner] ** 2 - rho**2)
        assert np.linalg.norm(start - center) == pytest.approx(cut)
        axis = (end - center) / np.linalg.norm(end - center)
        assert np.allclose((start - center) / np.linalg.norm(start - center), axis)
    middles = {tuple(np.round(e, 6)) for e in halves.end}
    assert len(middles) == 2  # each half ends at its bond's middle


def test_spheres_overlapping_past_the_middle_leave_no_half():
    structure = water()
    scene = build_scene(structure, bonds_for(structure), (1, 1, 1))
    radii = np.full(len(scene.positions), 0.1)
    radii[0] = 0.9  # the O sphere reaches past the middle of both O–H bonds (0.48 Å)
    halves = half_bonds(scene, radii, 0.05)
    assert len(halves) == 2 and 0 not in halves.owner.tolist()


def test_wire_does_not_cut_and_sticks_use_the_small_ball():
    structure = si()
    scene = build_scene(structure, bonds_for(structure), (1, 1, 1))
    wire = half_bonds(scene, drawn_radii(structure, scene, "fio"), BOND_RADIUS["fio"])
    assert np.allclose(wire.start, scene.positions[wire.owner])
    sticks = half_bonds(scene, drawn_radii(structure, scene, "vareta"), BOND_RADIUS["vareta"])
    cut = np.sqrt(STICK_RADIUS**2 - BOND_RADIUS["vareta"] ** 2)
    distance = np.linalg.norm(sticks.start - scene.positions[sticks.owner], axis=1)
    assert np.allclose(distance, cut)


def test_the_nearer_end_is_wider_in_perspective():
    quads = half_quads(
        np.array([[100.0, 100.0]]),
        np.array([[160.0, 100.0]]),
        np.array([1.3]),
        np.array([0.8]),
        0.1,
        100.0,
    )
    start, end = quads.width[0]
    assert start == pytest.approx(13.0) and end == pytest.approx(8.0)
    corners = quads.corners[0]
    assert np.linalg.norm(corners[0] - corners[3]) > np.linalg.norm(corners[1] - corners[2])


def test_a_half_seen_end_on_is_not_drawn():
    quads = half_quads(
        np.array([[50.0, 50.0], [50.0, 50.0]]),
        np.array([[50.3, 50.0], [60.0, 50.0]]),
        np.ones(2),
        np.ones(2),
        0.1,
        100.0,
    )
    assert quads.drawn.tolist() == [False, True]


# -- pixels --------------------------------------------------------------------------------------


def test_no_stick_inside_the_atom(view):
    with_bonds = pixels(view.render_image(SIZE))
    x, y = (round(v) for v in view.renderer.screen_position(AtomRef(0)))
    view.options.show_bonds = False
    view.refresh_options()
    without = pixels(view.render_image(SIZE))
    assert view.stats.bonds == 0
    assert with_bonds[y, x].tolist() == without[y, x].tolist()


def across(view, image, partner: int) -> list[list[int]]:
    """15 pixels across the O half of the O–``partner`` bond, beyond the O sphere."""
    o = np.array(view.renderer.screen_position(AtomRef(0)))
    h = np.array(view.renderer.screen_position(AtomRef(partner)))
    axis = (h - o) / np.linalg.norm(h - o)
    normal = np.array([-axis[1], axis[0]])
    point = o + axis * 0.4 * ZOOM  # O sphere: 0.30 Å; middle of the bond: 0.48 Å
    half_width = BOND_RADIUS["bola-vareta"] * ZOOM
    offsets = np.linspace(-0.9, 0.9, 15) * half_width
    spots = [point + normal * d for d in offsets]
    return [image[round(sy), round(sx)].tolist() for sx, sy in spots]


@pytest.mark.parametrize("turn", [0.0, 50.0, 115.0], ids=["0", "50", "115"])
def test_a_stick_is_shaded_like_a_cylinder(view, turn):
    angle = np.radians(turn)
    spin = np.array(
        [[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]]
    )
    view.camera.rotation = spin @ view.camera.rotation
    image = pixels(view.render_image(SIZE))
    for partner in (1, 2):
        row = across(view, image, partner)
        assert len({tuple(p) for p in row}) >= 3
        light = [luminance(p) for p in row]
        brightest = int(np.argmax(light))
        assert 0 < brightest < len(row) - 1  # the highlight is away from both edges
        assert light[0] < light[7] and light[-1] < light[7]  # both edges darker than the middle


def test_every_style_renders(view):
    for style in ("bola-vareta", "vareta", "fio", "espaco-cheio"):
        view.options.style = style
        view.refresh_options()
        image = pixels(view.render_image(SIZE))
        assert (image != image[0, 0]).any(axis=-1).sum() > 200
        assert view.stats.atoms == (
            0 if style == "fio" else 3
        )  # "fio": dots for unbonded atoms only


# -- spec 46 R2: the axes (a, b, c and x, y, z), their widths and the size of the labels -------------

VIEW = QSize(600, 480)
TRIAD = (slice(VIEW.height() - 110, VIEW.height()), slice(0, 110))  # rows, columns of the triad


def draw_si(marks=(), **options):
    """The cell of Si from its initial view, with ``options`` changed: (pixels, canvas)."""
    from qe_studio.ui.theme.manager import ThemeManager

    canvas = StructureCanvas(ThemeManager("dark"), si())
    canvas.resize(VIEW)
    for name, value in options.items():
        setattr(canvas.options, name, value)
    canvas.reset_view()
    canvas.set_marks(marks)
    return pixels(canvas.render_image(VIEW)), canvas


def without_triad(rgb: np.ndarray) -> np.ndarray:
    out = rgb.copy()
    out[TRIAD] = 0
    return out


def differing(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a != b).any(axis=2)


def test_the_defaults_are_the_widths_and_size_of_before():
    options = DisplayOptions()
    assert (options.abc_width, options.xyz_width, options.label_size) == (1.8, 2.0, 11)
    assert options.show_abc and options.show_xyz


def test_the_two_axis_systems_switch_independently():
    full, canvas = draw_si()
    primitives = canvas.stats.primitives

    no_abc, c_abc = draw_si(show_abc=False)
    assert c_abc.stats.primitives == primitives - 3  # the three arrows
    assert np.array_equal(no_abc[TRIAD], full[TRIAD])  # the triad is whole
    assert differing(without_triad(no_abc), without_triad(full)).any()  # arrows and names gone

    no_xyz, c_xyz = draw_si(show_xyz=False)
    assert c_xyz.stats.primitives == primitives
    assert np.array_equal(without_triad(no_xyz), without_triad(full))  # the arrows are whole
    assert differing(no_xyz[TRIAD], full[TRIAD]).any()  # the triad and its letters gone


def test_a_thicker_axis_paints_more_pixels_and_each_width_is_its_own():
    # the arrows: what differs from the same view without them (their names included, equal in both)
    none, _ = draw_si(show_abc=False)
    thin = int(differing(without_triad(draw_si(abc_width=1.8)[0]), without_triad(none)).sum())
    thick = int(differing(without_triad(draw_si(abc_width=6.0)[0]), without_triad(none)).sum())
    assert thick > thin
    # the triad: what differs from the view without it
    no_xyz = draw_si(show_xyz=False)[0][TRIAD]
    thin = int(differing(draw_si(xyz_width=2.0)[0][TRIAD], no_xyz).sum())
    thick = int(differing(draw_si(xyz_width=6.0)[0][TRIAD], no_xyz).sum())
    assert thick > thin
    # the other system does not move with a width
    default, _ = draw_si()
    assert np.array_equal(draw_si(abc_width=6.0)[0][TRIAD], default[TRIAD])
    assert np.array_equal(without_triad(draw_si(xyz_width=6.0)[0]), without_triad(default))


def test_label_size_grows_the_text_but_not_the_badge_of_a_measure():
    quiet = {"show_abc": False, "show_xyz": False}
    plain, _ = draw_si(**quiet)

    def box(rgb: np.ndarray) -> int:  # the area of the rectangle that holds every changed pixel
        rows, cols = np.nonzero(differing(plain, rgb))
        return int((rows.max() - rows.min() + 1) * (cols.max() - cols.min() + 1))

    small = box(draw_si(labels="simbolo", **quiet)[0])
    large = box(draw_si(labels="simbolo", label_size=20, **quiet)[0])
    assert large > small

    # the number of a badge sits in a disc of a fixed radius: it keeps its size
    ref = (AtomRef(0),)
    marked11, _ = draw_si(marks=ref, label_size=11, **quiet)
    marked20, _ = draw_si(marks=ref, label_size=20, **quiet)
    assert differing(marked11, plain).any()  # the ring and the badge are drawn
    assert np.array_equal(marked11, marked20)
    # ... while the names of the axes follow the size
    assert differing(draw_si(label_size=20)[0][TRIAD], draw_si()[0][TRIAD]).any()


# -- the ring of a fixed atom (spec 88) ------------------------------------------------------------

CENTER = 5.2917721  # the middle of the 20 bohr cube, Å
ATOMS_HEAD = """&CONTROL
/
&SYSTEM
  ibrav = 1, celldm(1) = 20.0, nat = {nat}, ntyp = 2
/
ATOMIC_SPECIES
O 15.999 O.UPF
H 1.008 H.UPF
ATOMIC_POSITIONS angstrom
"""
TWO_WATERS = (
    ATOMS_HEAD.format(nat=6)
    + """O 2.5000000 5.2917721 5.2917721{fixed}
H 3.4600000 5.2917721 5.2917721{fixed}
H 2.2596352 6.2211938 5.2917721{fixed}
O 8.0000000 5.2917721 5.2917721{free}
H 8.9600000 5.2917721 5.2917721{free}
H 7.7596352 6.2211938 5.2917721{free}
"""
)
PLAIN = {"perspective": False, "show_cell": False, "show_abc": False, "show_xyz": False}


def along_z(structure, zoom: float, center=None, **options) -> StructureCanvas:
    """A view along z, orthographic, without cell or axes, with these display options."""
    from qe_studio.ui.theme.manager import ThemeManager

    canvas = StructureCanvas(ThemeManager("dark"), structure, DisplayOptions(**(PLAIN | options)))
    canvas.render_image(SIZE)  # first frame
    canvas.camera.view_axis("z", np.eye(3))
    canvas.camera.center = np.full(3, CENTER) if center is None else center
    canvas.camera.zoom, canvas.camera.pan = zoom, np.zeros(2)
    return canvas


def waters(fixed=" 0 0 0", free=" 1 1 1", zoom=30.0, **options) -> StructureCanvas:
    """Two water molecules, one fixed, each on one half of the image."""
    return along_z(structure_of_text(TWO_WATERS.format(fixed=fixed, free=free)), zoom, **options)


def near(image, rgb, tolerance: int = 40) -> np.ndarray:
    return np.abs(pixels(image) - np.array(rgb)).max(axis=2) <= tolerance


def ring_by_side(canvas, rgb=FIXED_RING[True], **frame) -> tuple[int, int]:
    """Pixels of the ring color on the half of the fixed molecule and on the other."""
    mask = near(canvas.render_image(SIZE, **frame), rgb)
    middle = mask.shape[1] // 2
    left, right = int(mask[:, :middle].sum()), int(mask[:, middle:].sum())
    position = canvas.renderer.screen_position(AtomRef(0))
    assert position is not None
    return (left, right) if position[0] < SIZE.width() / 2 else (right, left)


def in_ring(mask: np.ndarray, x: float, y: float, radius_px: float) -> int:
    """Pixels of ``mask`` where the ring of an atom at (x, y) with this radius is drawn."""
    rows, columns = np.nonzero(mask)
    distance = np.hypot(columns + 0.5 - x, rows + 0.5 - y)
    ring = max(radius_px, MIN_PICK_RADIUS) + FIXED_GAP_PX
    return int((np.abs(distance - ring) <= FIXED_WIDTH / 2 + 1).sum())


@pytest.mark.parametrize("style", list(STYLES))
def test_only_the_fixed_atoms_have_a_ring(qapp, style):
    fixed, free = ring_by_side(waters(style=style, show_fixed=True))
    assert fixed > 30 and free == 0


def test_the_color_of_the_ring_goes_with_the_background(qapp):
    fixed, free = ring_by_side(waters(background="claro", show_fixed=True), FIXED_RING[False])
    assert fixed > 30 and free == 0
    assert FIXED_RING[True] != FIXED_RING[False]


def test_the_ring_is_just_outside_the_atom(qapp):
    canvas = waters(show_fixed=True)
    mask = near(canvas.render_image(SIZE), FIXED_RING[True])
    rows, columns = np.nonzero(mask)
    radii = drawn_radii(canvas.structure, canvas.scene) * canvas.camera.zoom
    for index in range(3):
        x, y = canvas.renderer.screen_position(AtomRef(index))
        ring = max(float(radii[index]), MIN_PICK_RADIUS) + FIXED_GAP_PX
        distance = np.hypot(columns + 0.5 - x, rows + 0.5 - y)
        around = distance[distance < ring + 6]  # the pixels of this atom's ring
        assert len(around) > 10
        assert np.abs(around - ring).max() <= FIXED_WIDTH / 2 + 1


def test_off_the_image_is_the_one_without_if_pos(qapp):
    plain = waters(fixed="", free="").render_image(SIZE)
    flagged = waters().render_image(SIZE)
    assert np.array_equal(pixels(flagged), pixels(plain))
    assert not near(flagged, FIXED_RING[True]).any()
    # on, an input that fixes nothing draws the same
    nothing = waters(fixed=" 1 1 1", show_fixed=True).render_image(SIZE)
    assert np.array_equal(pixels(nothing), pixels(plain))


def test_an_atom_in_front_covers_the_ring(qapp):
    """A fixed H and a free, larger O in line with the eye: no ring over the O when the H is behind it,
    and the whole ring when it is in front."""
    rings = {}
    for z in (CENTER - 2.0, CENTER + 2.0):
        text = (
            ATOMS_HEAD.format(nat=2)
            + f"O {CENTER} {CENTER} {CENTER} 1 1 1\nH {CENTER} {CENTER} {z} 0 0 0\n"
        )
        canvas = along_z(structure_of_text(text), ZOOM, show_fixed=True)
        assert len(canvas.scene.bond_a) == 0
        _xy, depth, _scale = canvas.camera.project(canvas.scene.positions, (400.0, 300.0))
        behind = bool(depth[1] > depth[0])
        rings[behind] = int(near(canvas.render_image(SIZE), FIXED_RING[True]).sum())
    assert rings[True] == 0 and rings[False] > 30


@pytest.mark.parametrize("frame", [{"draft": True}, {"dpr": 2.0}], ids=["draft", "print"])
def test_the_ring_is_in_every_kind_of_frame(qapp, frame):
    fixed, free = ring_by_side(waters(show_fixed=True), **frame)
    assert fixed > 30 and free == 0


def test_a_hidden_species_has_no_ring(qapp):
    fixed, free = ring_by_side(waters(show_fixed=True, species_hidden={0, 1}))
    assert fixed == free == 0


def test_every_copy_of_a_fixed_atom_has_a_ring(qapp):
    canvas = waters(zoom=15.0, show_fixed=True, reps=(2, 1, 1))
    canvas.camera.center = canvas.scene.box_corners(canvas.scene.block).mean(axis=0)
    mask = near(canvas.render_image(SIZE), FIXED_RING[True])
    radii = drawn_radii(canvas.structure, canvas.scene) * canvas.camera.zoom

    def rings_of(index: int, shift: tuple[int, int, int]) -> int:
        x, y = canvas.renderer.screen_position(AtomRef(index, shift))
        return in_ring(mask, x, y, float(radii[index]))

    assert rings_of(0, (0, 0, 0)) > 5 and rings_of(0, (1, 0, 0)) > 5
    assert rings_of(3, (0, 0, 0)) == 0 and rings_of(3, (1, 0, 0)) == 0


def test_a_ghost_of_a_fixed_atom_has_a_faint_ring(qapp):
    # a bond across the boundary of a: the ghost past x = 15 Å is the fixed atom's
    structure = make_structure(
        np.eye(3) * 15, [[0.05, 0.5, 0.5], [0.95, 0.5, 0.5]], ["C", "C"], ((0, 0, 0), (1, 1, 1))
    )
    canvas = along_z(structure, 20.0, center=np.full(3, 7.5), show_fixed=True)
    image = canvas.render_image(SIZE)
    scene = canvas.scene
    assert scene.n_ghost == 2
    xy, _depth, _scale = canvas.camera.project(scene.positions, (400.0, 300.0))
    faint = GHOST_OPACITY * np.array(FIXED_RING[True]) + (1 - GHOST_OPACITY) * np.array(
        BACKGROUND[True]
    )
    radii = drawn_radii(structure, scene) * canvas.camera.zoom
    ghosts = np.arange(scene.n_real, len(scene.positions))
    fixed_ghost = ghosts[scene.fixed[ghosts]][0]
    free_ghost = ghosts[~scene.fixed[ghosts]][0]
    assert in_ring(near(image, faint, 15), *xy[fixed_ghost], float(radii[fixed_ghost])) > 5
    assert in_ring(near(image, FIXED_RING[True]), *xy[fixed_ghost], float(radii[fixed_ghost])) == 0
    assert in_ring(near(image, faint, 15), *xy[free_ghost], float(radii[free_ghost])) == 0
