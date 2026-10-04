"""Spec 25 R5: the band path pymatgen suggests, in the input's reciprocal coordinates, and the
K_POINTS cards."""

import sys
import warnings

import numpy as np
import pytest

from qe_studio.core.calc_create.kpath import (
    KMesh,
    KPath,
    KPathUnavailable,
    KPoint,
    label_of,
    suggest_path,
    to_card,
)
from qe_studio.core.calc_create.types import by_id
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.lattice import BOHR_ANGSTROM, Crystal, cell_vectors, crystal_from_editor
from qe_studio.core.qe.pw_input import parse_kpoints, read_input

from calc_helpers import AL_PATH, JOBS, al, ni
from conftest import FIXTURES


def reciprocal(cell):
    return 2 * np.pi * np.linalg.inv(cell).T


def pymatgen_path(crystal):
    """Labels → cartesian k of pymatgen's own path (its standard primitive cell)."""
    from pymatgen.core import Lattice, Structure
    from pymatgen.symmetry.bandstructure import HighSymmKpath

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        structure = Structure(Lattice(crystal.cell), ["Al"] * len(crystal.labels), crystal.frac)
        kpath = HighSymmKpath(structure, path_type="setyawan_curtarolo")
    rec = kpath.prim.lattice.reciprocal_lattice.matrix
    return {name: np.asarray(k) @ rec for name, k in kpath.kpath["kpoints"].items()}


def segment_lengths(path: KPath, cell) -> list[float]:
    rec = reciprocal(cell)
    ks = [np.asarray(p.frac) @ rec for p in path.points]
    return [
        float(np.linalg.norm(ks[i + 1] - ks[i])) for i in range(len(ks) - 1) if i not in path.breaks
    ]


def test_fcc_path_of_aluminium():
    crystal = al().crystal
    path = suggest_path(crystal)
    labels = [p.label for p in path.points]
    assert {"Gamma", "X", "W", "K", "L", "U"} <= set(labels)
    assert labels == ["Gamma", "X", "W", "K", "Gamma", "L", "U", "W", "L", "K", "U", "X"]
    assert path.breaks == frozenset({9})  # K|U
    assert {p.npts for p in path.points} == {20}
    assert path.warnings == ()  # QE's ibrav = 2 cell is pymatgen's standard one


def test_points_keep_their_distances_in_the_input_cell():
    """Each point and each segment has the length pymatgen gives in its own cell: the conversion
    is a change of basis of the same reciprocal lattice."""
    crystal = al().crystal
    path = suggest_path(crystal)
    theirs = pymatgen_path(crystal)
    rec = reciprocal(crystal.cell)
    for point in path.points:
        name = "\\Gamma" if point.label == "Gamma" else point.label
        ours = np.asarray(point.frac) @ rec
        assert np.linalg.norm(ours) == pytest.approx(np.linalg.norm(theirs[name]), abs=1e-9)
    names = [("\\Gamma" if p.label == "Gamma" else p.label) for p in path.points]
    expected = [
        float(np.linalg.norm(theirs[names[i + 1]] - theirs[names[i]]))
        for i in range(len(names) - 1)
        if i not in path.breaks
    ]
    assert segment_lengths(path, crystal.cell) == pytest.approx(expected, abs=1e-9)


def test_a_rotated_cell_gets_converted_points():
    """ibrav = -3 (bcc with other vectors) is not pymatgen's standard: points are converted."""
    cell = cell_vectors(-3, [6.0]) * BOHR_ANGSTROM
    crystal = Crystal(cell, ("Fe",), np.zeros((1, 3)))
    path = suggest_path(crystal)
    assert {"Gamma", "H", "N", "P"} <= {p.label for p in path.points}
    rec = reciprocal(cell)
    h = next(p for p in path.points if p.label == "H")
    assert np.linalg.norm(np.asarray(h.frac) @ rec) == pytest.approx(
        2 * np.pi / (6.0 * BOHR_ANGSTROM)
    )


def test_supercell_and_magnetic_labels_warn():
    conventional = cell_vectors(1, [7.63]) * BOHR_ANGSTROM
    frac = np.array([[0, 0, 0], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]])
    path = suggest_path(Crystal(conventional, ("Ni1", "Ni2", "Ni1", "Ni2"), frac))
    assert any("4× o volume" in w for w in path.warnings)
    assert any("Ni1, Ni2 tratados como Ni" in w for w in path.warnings)


def test_triclinic_kaolinite():
    text = (FIXTURES / "kao_vc_relax" / "vc-relax.in").read_text()
    path = suggest_path(crystal_from_editor(InputEditor.from_text(text)))
    assert "Gamma" in {p.label for p in path.points}
    assert len(path.points) >= 4


def test_unavailable_paths(monkeypatch):
    with pytest.raises(KPathUnavailable, match="estrutura do SCF"):
        suggest_path(None)
    with pytest.raises(KPathUnavailable, match="não é um elemento"):
        suggest_path(Crystal(np.eye(3) * 4, ("Qq",), np.zeros((1, 3))))
    monkeypatch.setitem(sys.modules, "pymatgen.symmetry.bandstructure", None)
    with pytest.raises(KPathUnavailable, match="pymatgen não está instalado"):
        suggest_path(al().crystal)


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
    assert label_of("\\Gamma") == "Gamma" and label_of("\\Sigma_1") == "Sigma_1"


def test_lain_reads_the_labels_of_the_generated_bands_input(tmp_path):
    bands = by_id("bandas").plan(al(), {"kpath": AL_PATH}, JOBS).file("bands.in")
    path = tmp_path / "bands.in"
    path.write_text(bands.text)
    card = read_input(path).kpoints
    assert card.is_path and card.labels == ("L", "Gamma", "X", "U", "Gamma")
    assert card.vertex_indices() == [0, 20, 50, 60, 90]
    original = read_input(FIXTURES / "al_bands" / "al.band.in").kpoints
    assert card.path_length == original.path_length  # the fixture's .gnu fits it


def test_spin_path_is_the_same():
    assert [p.label for p in suggest_path(ni().crystal).points][:4] == ["Gamma", "X", "W", "K"]


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
