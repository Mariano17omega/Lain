"""Spec 74 R1: the CIF of a pw.x input."""

import numpy as np
import pytest
from ase.io import read

from qe_studio.core.structure3d.cif import CifError, cif_text, write_cif
from qe_studio.core.structure3d.source import read_structure
from structure3d_helpers import make_structure

from conftest import FIXTURES, copy_fixture

CASES = ["si_bands/si.scf.in", "kao_surface_inputs/scf-kaolinite.in"]


@pytest.mark.parametrize("rel", CASES)
def test_ase_reads_back_the_same_structure(tmp_path, rel):
    folder, name = rel.split("/")
    path = copy_fixture(folder, tmp_path) / name
    structure = read_structure(path)
    written = write_cif(path)
    assert written == path.with_suffix(".cif")
    atoms = read(written, format="cif")
    # a CIF keeps lengths and angles, not the orientation: compare those and the fractions
    assert np.allclose(atoms.cell.cellpar(), structure.lattice_parameters, atol=1e-6)
    delta = atoms.get_scaled_positions(wrap=False) - structure.frac
    assert np.allclose(delta, np.round(delta), atol=1e-5)
    assert list(atoms.get_chemical_symbols()) == list(structure.symbols)
    assert len(atoms) == structure.source.nat
    text = written.read_text()
    assert text.startswith(f"# Gerado pelo Lain a partir de {name}\n")
    assert sum(1 for line in text.splitlines() if line.endswith(" 1.0")) == len(structure)


def test_an_unknown_label_is_an_error_and_writes_nothing(tmp_path):
    path = copy_fixture("si_bands", tmp_path) / "si.scf.in"
    path.write_text(path.read_text().replace("Si ", "X ").replace(" Si", " X"))
    with pytest.raises(CifError, match="X"):
        write_cif(path)
    assert not list(tmp_path.rglob("*.cif"))


def test_it_never_overwrites(tmp_path):
    path = copy_fixture("si_bands", tmp_path) / "si.scf.in"
    first, second = write_cif(path), write_cif(path)
    assert (first.name, second.name) == ("si.scf.cif", "si.scf_2.cif")


def test_the_text_does_not_depend_on_the_language():
    from qe_studio import i18n

    structure = read_structure(FIXTURES / "si_bands/si.scf.in")
    before = cif_text(structure)
    i18n.install("en")
    try:
        assert cif_text(structure) == before
    finally:
        i18n.install("pt")


def site_labels(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.endswith(" 1.0")]


def test_labels_ending_in_a_digit_stay_unique(tmp_path):
    """Atom 12 ``O1`` and atom 2 ``O11`` would both be ``O112``; ``O43`` stays as spec 74 has it."""
    names = ["Si", "O11", *["Si"] * 9, "O1", "O"]
    frac = [[i / len(names), 0.0, 0.0] for i in range(len(names))]
    structure = make_structure(np.eye(3) * 5.0, frac, names)
    text = cif_text(structure)
    found = site_labels(text)
    assert len(set(found)) == len(names)
    assert (found[0], found[1], found[11], found[12]) == ("Si1", "O11_2", "O1_12", "O13")
    path = tmp_path / "x.cif"
    path.write_text(text)
    assert list(read(path, format="cif").get_chemical_symbols()) == list(structure.symbols)
