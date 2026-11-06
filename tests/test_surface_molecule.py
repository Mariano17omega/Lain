"""Spec 75 R3: the molecule's anchor by its number in the SCF, its label or both (``anchor_index``),
on the H3CHg molecule (Hg C H H H)."""

from __future__ import annotations

import numpy as np
import pytest

from qe_studio.core.calc_create.surface import SurfaceError
from qe_studio.core.calc_create.surface.molecule import anchor_index, molecule_of

from surface_helpers import MOLECULE, read

LABELS = ("Hg", "C", "H", "H", "H")


@pytest.mark.parametrize(
    "text, index",
    [("", None), ("  ", None), ("1", 0), ("hg", 0), ("Hg", 0), ("C", 1), ("H4", 3), ("h 5", 4)],
)
def test_the_anchor_by_number_or_label(text, index):
    assert anchor_index(LABELS, text) == index


@pytest.mark.parametrize(
    "text, message",
    [
        ("H", "O rótulo H aparece em 3 átomos (3, 4, 5): use o número ou H3"),
        ("C3", "O átomo 3 é H, não C"),
        ("O", "Nenhum átomo O na molécula (rótulos: Hg, C, H)"),
        ("X2", "Nenhum átomo X2 na molécula (rótulos: Hg, C, H)"),
        ("9", "Átomo âncora 9 fora da molécula (1 a 5)"),
        ("0", "Átomo âncora 0 fora da molécula (1 a 5)"),
        ("H9", "Átomo âncora 9 fora da molécula (1 a 5)"),
    ],
)
def test_an_anchor_that_names_no_single_atom(text, message):
    with pytest.raises(SurfaceError) as caught:
        anchor_index(LABELS, text)
    assert str(caught.value) == message


def test_the_whole_label_comes_before_its_number():
    """``Fe1`` is the label Fe1, not atom 1 of a label Fe."""
    labels = ("O", "Fe1", "Fe2")
    assert anchor_index(labels, "Fe1") == 1
    assert anchor_index(labels, "fe2") == 2


def test_the_molecule_by_a_label():
    """The C as the anchor: at the origin, the axis to the Hg (the first heavy atom besides it)."""
    molecule = molecule_of(read(MOLECULE), "C")
    assert molecule.anchor == 1
    assert np.allclose(molecule.coords[1], 0.0)
    hg = molecule.coords[0]
    assert np.allclose(hg / np.linalg.norm(hg), [0.0, 0.0, 1.0], atol=1e-9)
    assert molecule_of(read(MOLECULE), "").anchor == molecule_of(read(MOLECULE)).anchor == 0
