import numpy as np
import pytest
from PyQt6.QtCore import QSize

from viewer3d.core.structure import AtomRef
from viewer3d.ui.canvas import Canvas


def pixels(image):
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    # copy: the view must not outlive the QImage that owns the memory
    return np.frombuffer(ptr, dtype=np.uint8).reshape(image.height(), image.width(), 4).copy()


@pytest.fixture
def canvas(qapp, si):
    widget = Canvas()
    widget.resize(600, 500)
    widget.set_structure(si)
    return widget


def test_frame_is_not_uniform_and_has_expected_primitives(canvas):
    image = canvas.render_image(QSize(600, 500))
    px = pixels(image)
    assert len(np.unique(px.reshape(-1, 4), axis=0)) > 10
    stats = canvas.stats
    assert stats.atoms == 2
    assert stats.ghosts > 0
    assert stats.bonds > 0 and stats.primitives > stats.atoms
    assert stats.ms > 0


@pytest.mark.parametrize("style", ["bola-vareta", "vareta", "fio", "espaco-cheio"])
def test_every_style_renders(canvas, style):
    canvas.options.style = style
    canvas.refresh_options()
    px = pixels(canvas.render_image(QSize(400, 300)))
    background = px[0, 0]
    assert (px != background).any(axis=-1).sum() > 200


def test_repeat_doubles_drawn_atoms(canvas):
    canvas.render_image(QSize(600, 500))
    one = canvas.stats.atoms
    canvas.options.reps = (2, 1, 1)
    canvas.refresh_options()
    canvas.render_image(QSize(600, 500))
    assert canvas.stats.atoms == 2 * one


def test_draft_mode_draws_and_differs(canvas):
    full = pixels(canvas.render_image(QSize(500, 400)))
    draft = pixels(canvas.render_image(QSize(500, 400), draft=True))
    assert canvas.stats.draft is True
    assert not np.array_equal(full, draft)


def test_pick_returns_the_atom_at_its_screen_position(canvas):
    # the isometric view looks along (1,1,1), where both Si atoms overlap exactly
    canvas.camera.view_axis("x", np.eye(3))
    canvas.render_image(QSize(600, 500))
    for index in range(2):
        ref = AtomRef(index)
        pos = canvas.renderer.screen_position(ref)
        assert pos is not None
        assert canvas.renderer.pick(pos) == ref
    assert canvas.renderer.pick((1.0, 1.0)) is None


def test_hidden_species_is_not_drawn_or_picked(canvas):
    canvas.render_image(QSize(600, 500))
    pos = canvas.renderer.screen_position(AtomRef(0))
    canvas.options.species_hidden = {0}
    canvas.render_image(QSize(600, 500))
    assert canvas.stats.atoms == 0
    assert canvas.renderer.pick(pos) is None


def test_kaolinite_renders(qapp, kaolinite):
    widget = Canvas()
    widget.resize(800, 600)
    widget.set_structure(kaolinite)
    px = pixels(widget.render_image(QSize(800, 600)))
    assert (px != px[0, 0]).any(axis=-1).sum() > 2000
    assert widget.stats.atoms == 72
