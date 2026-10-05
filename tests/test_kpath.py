"""Spec 25 R5 and spec 27-2: the K_POINTS cards, and the checks of a typed band path against the x axis
bands.x draws (collapsed segments, "Distribuir pelo comprimento")."""

from dataclasses import replace

import numpy as np
import pytest

from qe_studio.core.calc_create.kpath import (
    MAX_NPTS,
    CollapsedSegment,
    KMesh,
    KPath,
    KPoint,
    _expand,
    _reciprocal,
    collapse_note,
    collapsed_segments,
    distribute,
    segment_progress,
    to_card,
)
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.qe.pw_input import parse_kpoints, read_input

from calc_helpers import AL_PATH, JOBS, al, hex_cell, hex_path
from conftest import FIXTURES


def reciprocal(cell):
    return 2 * np.pi * np.linalg.inv(cell).T


def segment_lengths(path: KPath, cell) -> list[float]:
    rec = reciprocal(cell)
    ks = [np.asarray(p.frac) @ rec for p in path.points]
    return [
        float(np.linalg.norm(ks[i + 1] - ks[i])) for i in range(len(ks) - 1) if i not in path.breaks
    ]


def test_hexagonal_path_with_uniform_points_collapses_a_to_l():
    """c/a = 6.33: A→L is 7× the Γ–A segment before it, at the same points each, so bands.x takes
    its steps for a jump and the segment gets no length on the x axis."""
    cell, path = hex_cell(), hex_path()
    found = collapsed_segments(path, cell)
    assert [(s.a, s.b) for s in found] == [(4, 5)]
    assert found[0].lost == pytest.approx(1.0)
    progress = {(s.a, s.b): s for s in segment_progress(path, cell)}
    assert progress[(4, 5)].advance == pytest.approx(0.0)
    assert progress[(0, 1)].advance == pytest.approx(progress[(0, 1)].real)
    note = collapse_note(path, found[0])
    assert note.startswith(
        "Segmento A→L colapsa no eixo x do bands.x (passo maior que 5× o anterior)"
    )
    assert "‘Distribuir pelo comprimento’" in note
    assert collapse_note(path, CollapsedSegment(3, 4, 1.0)).startswith("Segmento Γ→A ")
    unnamed = KPath((path.points[0], replace(path.points[1], label="")))
    assert collapse_note(unnamed, CollapsedSegment(0, 1, 1.0)).startswith("Segmento Γ→ponto 2 ")


def test_distribute_gives_every_hexagonal_segment_its_length_on_the_x_axis():
    cell, path = hex_cell(), hex_path()
    spread = distribute(path, cell, 25)
    expected = [max(2, round(length * 25)) for length in segment_lengths(path, cell)]
    assert [p.npts for p in spread.points[:-1]] == expected
    assert collapsed_segments(spread, cell) == []
    assert all(s.advance >= 0.95 * s.real for s in segment_progress(spread, cell))
    assert [(p.label, p.frac) for p in spread.points] == [(p.label, p.frac) for p in path.points]


def test_aluminium_path_has_nothing_to_warn_about_before_or_after_distribute():
    cell = al().crystal.cell
    assert collapsed_segments(AL_PATH, cell) == []
    spread = distribute(AL_PATH, cell, 25)
    assert collapsed_segments(spread, cell) == []
    assert [p.npts for p in spread.points[:-1]] == [
        max(2, round(length * 25)) for length in segment_lengths(AL_PATH, cell)
    ]
    assert (spread.breaks, spread.warnings) == (AL_PATH.breaks, AL_PATH.warnings)
    assert [(p.label, p.frac) for p in spread.points] == [(p.label, p.frac) for p in AL_PATH.points]
    option, body = to_card(spread)
    card = parse_kpoints([f"K_POINTS {option}", *body])
    assert body[0] == str(len(AL_PATH.points)) and card.labels == ("L", "Gamma", "X", "U", "Gamma")
    kpoints, vertices = _expand(spread, _reciprocal(cell))
    assert int(card.weights.sum()) == len(kpoints) == sum(spread.weights())  # pw.x's nks
    assert vertices == [int(v) for v in np.cumsum([0, *spread.weights()[:-1]])]


def test_a_break_is_not_a_segment():
    cell = al().crystal.cell
    path = replace(AL_PATH, breaks=frozenset({2}))
    assert [(s.a, s.b) for s in segment_progress(path, cell)] == [(0, 1), (1, 2), (3, 4)]
    spread = distribute(path, cell, 25)
    assert spread.points[2].npts == AL_PATH.points[2].npts  # before a break: weight 1, untouched
    assert spread.points[-1].npts == AL_PATH.points[-1].npts
    assert spread.breaks == path.breaks
    assert len(_expand(spread, _reciprocal(cell))[0]) == sum(spread.weights())


def test_distribute_bounds():
    cell = al().crystal.cell
    assert max(p.npts for p in distribute(AL_PATH, cell, 1e6).points) == MAX_NPTS
    short = KPath(
        (KPoint("a", (0, 0, 0), 20), KPoint("b", (0.001, 0, 0), 20), KPoint("c", (0.5, 0, 0)))
    )
    assert distribute(short, cell, 25).points[0].npts == 2  # min_pts
    assert distribute(short, cell, 25, min_pts=5).points[0].npts == 5


def test_the_checks_never_raise():
    cell = al().crystal.cell
    one = KPath((KPoint("Gamma", (0, 0, 0)),))
    for path in (KPath(()), one):
        assert segment_progress(path, cell) == [] and distribute(path, cell, 25) == path
    singular = np.zeros((3, 3))
    assert (
        collapsed_segments(AL_PATH, singular) == [] and distribute(AL_PATH, singular, 25) == AL_PATH
    )
    assert distribute(AL_PATH, cell, 0) == AL_PATH
    assert distribute(AL_PATH, cell, float("nan")) == AL_PATH
    same = KPath((KPoint("a", (0, 0, 0), 5), KPoint("b", (0, 0, 0), 5)))
    assert collapsed_segments(same, cell) == []  # no steps
    bad = KPath((KPoint("a", (0, 0, 0)), KPoint("b", (float("nan"), 0, 0))))
    assert segment_progress(bad, cell) == [] and distribute(bad, cell, 25) == bad


def test_card_weights_and_labels():
    path = KPath(
        (
            KPoint("Gamma", (0, 0, 0), 30),
            KPoint("X", (0.5, 0, 0.5), 10),
            KPoint("U", (0.625, 0.25, 0.625), 15),
            KPoint("", (-0.0, 0.5, 0), 7),
        ),
        frozenset({1}),
    )
    option, body = to_card(path)
    assert option == "crystal_b"
    assert body == [
        "4",
        " 0.00000000  0.00000000  0.00000000   30  ! Gamma",
        " 0.50000000  0.00000000  0.50000000    1  ! X",
        " 0.62500000  0.25000000  0.62500000   15  ! U",
        " 0.00000000  0.50000000  0.00000000    1",
    ]
    card = parse_kpoints([f"K_POINTS {option}", *body])
    assert card.labels == ("Gamma", "X", "U", "")
    assert card.weights.tolist() == [30, 1, 15, 1]


def test_lain_reads_the_labels_of_the_generated_bands_input(tmp_path):
    bands = by_id("bandas").plan(al(), {"kpath": AL_PATH}, JOBS).file("bands.in")
    path = tmp_path / "bands.in"
    path.write_text(bands.text)
    card = read_input(path).kpoints
    assert card.is_path and card.labels == ("L", "Gamma", "X", "U", "Gamma")
    assert card.vertex_indices() == [0, 20, 50, 60, 90]
    original = read_input(FIXTURES / "al_bands" / "al.band.in").kpoints
    assert card.path_length == original.path_length  # the fixture's .gnu fits it


def test_mesh_card_and_parse():
    mesh = KMesh((8, 8, 4), (1, 1, 0))
    assert mesh.card() == ("automatic", ["8 8 4 1 1 0"])
    assert KMesh.parse("8 8 4 1 1 0") == mesh
    assert KMesh.parse("8 8 8") == KMesh((8, 8, 8))
    assert KMesh.parse("8 8") is None and KMesh.parse("a b c") is None
    assert mesh.count == 256
    assert KMesh((0, 1, 1)).problems() and KMesh((2, 2, 2), (2, 0, 0)).problems()
    card = parse_kpoints(["K_POINTS automatic", *mesh.card()[1]])
    assert card.points.tolist() == [[8, 8, 4]] and card.weights.tolist() == [1, 1, 0]
