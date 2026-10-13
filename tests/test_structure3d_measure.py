"""Spec 44 R1: distances, angles and the measures of a window (pairs and trios, in click order)."""

import math

import numpy as np
import pytest

from qe_studio.core.structure3d.bonds import BondGraph, bonds_for
from qe_studio.core.structure3d.measure import angle, distance
from qe_studio.core.structure3d.measurements import Measurement, Measurer, row_text, to_tsv
from qe_studio.core.structure3d.model import AtomRef
from structure3d_helpers import si, water

BOHR = 0.529177210903
SI_BOND = np.sqrt(3) / 4 * 10.16863713 * BOHR  # √3/4 · the cubic lattice parameter
TETRAHEDRAL = math.degrees(math.acos(-1 / 3))  # 109.47°


def test_diamond_bond_and_tetrahedral_angle():
    structure = si()
    assert distance(structure, AtomRef(0), AtomRef(1)) == pytest.approx(SI_BOND)
    near = [ref for ref, _d in BondGraph(bonds_for(structure), 2).neighbors(AtomRef(1))]
    assert len(near) == 4 and any(ref.shift != (0, 0, 0) for ref in near)
    for a, c in [(near[0], near[1]), (near[1], near[3]), (near[2], near[3])]:
        assert angle(structure, a, AtomRef(1), c) == pytest.approx(TETRAHEDRAL)
        assert angle(structure, a, AtomRef(1), c) == pytest.approx(
            angle(structure, c, AtomRef(1), a)
        )
    assert round(TETRAHEDRAL, 2) == 109.47


def test_an_angle_with_a_zero_arm_is_undefined():
    structure = si()
    assert math.isnan(angle(structure, AtomRef(0), AtomRef(0), AtomRef(1)))


def test_without_a_mode_nothing_is_measured():
    measurer = Measurer(si())
    assert measurer.mode is None
    assert measurer.click(AtomRef(0)) is None and measurer.pending == ()


def test_pairs_are_independent():
    structure = water()
    measurer = Measurer(structure)
    measurer.set_mode("distancia")
    clicks = [AtomRef(0), AtomRef(1), AtomRef(0), AtomRef(2)]
    made = [m for ref in clicks if (m := measurer.click(ref)) is not None]
    assert [m.refs for m in made] == [(AtomRef(0), AtomRef(1)), (AtomRef(0), AtomRef(2))]
    assert [m.value for m in made] == pytest.approx([0.96, 0.96])
    assert measurer.pending == ()


def test_trios_are_independent_and_the_vertex_is_the_second():
    structure = water()
    measurer = Measurer(structure)
    measurer.set_mode("angulo")
    clicks = [AtomRef(1), AtomRef(0), AtomRef(2), AtomRef(0), AtomRef(1), AtomRef(2)]
    made = [m for ref in clicks if (m := measurer.click(ref)) is not None]
    assert len(made) == 2
    assert made[0].value == pytest.approx(104.5, abs=1e-3)  # H–O–H, vertex at O
    assert made[1].value == pytest.approx(angle(structure, AtomRef(0), AtomRef(1), AtomRef(2)))


def test_a_repeated_atom_is_ignored():
    measurer = Measurer(water())
    measurer.set_mode("distancia")
    assert measurer.click(AtomRef(0)) is None
    assert measurer.click(AtomRef(0)) is None
    assert measurer.pending == (AtomRef(0),)
    assert measurer.click(AtomRef(0, (1, 0, 0))) is not None  # another copy is another atom


def test_changing_the_mode_drops_the_pending_atoms():
    measurer = Measurer(water())
    measurer.set_mode("distancia")
    measurer.click(AtomRef(0))
    measurer.set_mode("angulo")
    assert measurer.pending == ()
    assert measurer.click(AtomRef(1)) is None and measurer.click(AtomRef(2)) is None
    assert measurer.pending == (AtomRef(1), AtomRef(2))
    measurer.clear_pending()
    assert measurer.pending == ()


def test_row_text_and_tsv():
    structure = water()
    pair = Measurement("distancia", (AtomRef(0), AtomRef(1)), 0.96)
    trio = Measurement("angulo", (AtomRef(1), AtomRef(0), AtomRef(2)), 104.5)
    undefined = Measurement("angulo", (AtomRef(0), AtomRef(0, (1, 0, 0)), AtomRef(0)), math.nan)
    assert row_text(structure, pair) == ("O1 - H2", "0.960 Å")
    assert row_text(structure, trio) == ("H2 - O1 - H3", "104.50°")
    assert row_text(structure, undefined) == ("O1 - O1(1,0,0) - O1", "—")
    assert to_tsv(structure, [pair, trio, undefined]) == (
        "Medida\tÁtomos\tValor\n"
        "Distância\tO1 - H2\t0.960\n"
        "Ângulo\tH2 - O1 - H3\t104.50\n"
        "Ângulo\tO1 - O1(1,0,0) - O1\t\n"
    )
