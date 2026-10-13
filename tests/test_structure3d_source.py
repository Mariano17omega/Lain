"""Spec 43 R1: the structure of every pw.x input of the fixtures, read without ASE."""

import subprocess
import sys

import numpy as np
import pytest

from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.lattice import crystal_from_editor
from qe_studio.core.sniff import INPUT_READ_LIMIT
from qe_studio.core.structure3d.model import AtomRef, atom_name
from qe_studio.core.structure3d.source import StructureReadError, read_structure, structure_of_text
from structure3d_helpers import NI_SCF, PW_INPUTS, SI_SCF, SLAB_2X1

from conftest import FIXTURES


@pytest.mark.parametrize("path", PW_INPUTS, ids=lambda p: p.name)
def test_every_pw_input_matches_the_crystal(path):
    structure = read_structure(path)
    crystal = crystal_from_editor(InputEditor.from_text(path.read_text()))
    assert np.allclose(structure.cell, crystal.cell)
    assert np.allclose(structure.frac, crystal.frac)
    assert structure.labels == crystal.labels
    assert structure.source.nat == len(crystal.labels)
    assert structure.source.path == str(path)
    assert {s.label for s in structure.species} >= set(structure.labels)


def test_any_calculation_is_read():
    calculations = {read_structure(path).source.calculation for path in PW_INPUTS}
    assert {"scf", "nscf", "bands", "relax", "vc-relax"} <= calculations


def test_fixed_atoms_have_their_flags():
    structure = read_structure(SLAB_2X1)
    lines = SLAB_2X1.read_text().splitlines()
    first = lines.index(next(line for line in lines if line.startswith("ATOMIC_POSITIONS")))
    index = 48 - 1 - first - 1  # line 48 of the file, 0-based atom
    assert lines[47].split()[0] == "Si"
    assert structure.flags[index] == (0, 0, 0)
    assert structure.has_flags
    assert structure.flags[0] is None  # a row without if_pos


def test_species_mass_and_pseudo():
    structure = read_structure(SI_SCF)
    (species,) = structure.species
    assert (species.label, species.mass, species.pseudo, species.number) == (
        "Si",
        28.086,
        "Si.pz-rrkj.UPF",
        1,
    )
    assert structure.source.prefix == "silicon"
    assert structure.source.ibrav == 2
    assert structure.source.starting_magnetization == {}
    assert not structure.has_flags


def test_starting_magnetization():
    structure = read_structure(NI_SCF)
    assert structure.source.starting_magnetization == {1: 0.8}
    assert structure.source.nspin == 2


def test_formula_volume_and_parameters():
    structure = read_structure(SI_SCF)
    a = 10.16863713 * 0.529177210903
    assert structure.formula == "Si2"
    assert structure.volume == pytest.approx(a**3 / 4)
    la, lb, lc, alpha, beta, gamma = structure.lattice_parameters
    assert la == pytest.approx(a / np.sqrt(2)) and lb == pytest.approx(la)
    assert alpha == pytest.approx(60.0) and gamma == pytest.approx(60.0)


def test_atom_names_are_qe_numbers():
    structure = read_structure(SLAB_2X1)
    assert atom_name(structure, AtomRef(42)) == "O43"
    assert atom_name(structure, AtomRef(42, (1, 0, 0))) == "O43(1,0,0)"
    unknown = structure_of_text(SI_TEXT.replace("Si", "X"))
    assert atom_name(unknown, AtomRef(1)) == "X2"
    assert unknown.source.warnings == ("Espécie sem elemento conhecido: X (cinza, raio 1,0 Å)",)


SI_TEXT = SI_SCF.read_text()


def test_a_position_label_without_species_row_is_kept_with_a_warning():
    text = SI_TEXT.replace(" Si 0.25  0.25 0.25", " Ge 0.25  0.25 0.25")
    structure = structure_of_text(text)
    germanium = structure.species[1]
    assert (germanium.label, germanium.mass, germanium.pseudo, germanium.number) == (
        "Ge",
        None,
        None,
        2,
    )
    assert structure.source.warnings == (
        "Espécie Ge sem linha em ATOMIC_SPECIES (massa e pseudopotencial vazios)",
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            SI_TEXT.split("ATOMIC_POSITIONS")[0],
            "Estrutura de si.scf.in ilegível: sem ATOMIC_POSITIONS",
        ),
        (
            SI_TEXT.replace("ATOMIC_POSITIONS", "ATOMIC_POSITIONS crystal_sg"),
            "Estrutura de si.scf.in ilegível: ATOMIC_POSITIONS crystal_sg não é suportado",
        ),
        (
            (FIXTURES / "si_bands" / "bands.in").read_text(),
            "si.scf.in não é um input do pw.x (sem &SYSTEM)",
        ),
    ],
    ids=["sem-posicoes", "crystal-sg", "bands-x"],
)
def test_errors_are_portuguese_sentences(tmp_path, text, message):
    path = tmp_path / "si.scf.in"
    path.write_text(text)
    with pytest.raises(StructureReadError) as error:
        read_structure(path)
    assert str(error.value) == message


def test_too_big_and_missing_files(tmp_path):
    big = tmp_path / "grande.in"
    big.write_text(SI_TEXT + "!" * INPUT_READ_LIMIT)
    with pytest.raises(StructureReadError, match="grande.in passa de 2 MB"):
        read_structure(big)
    with pytest.raises(StructureReadError, match="Não foi possível ler sumiu.in"):
        read_structure(tmp_path / "sumiu.in")


def test_importing_the_package_loads_neither_ase_nor_scipy():
    code = (
        "import sys, qe_studio.core.structure3d.source, qe_studio.core.structure3d.bonds, "
        "qe_studio.core.structure3d.replicate, qe_studio.core.structure3d.geometry, "
        "qe_studio.core.structure3d.camera, qe_studio.core.structure3d.pick, "
        "qe_studio.core.structure3d.options; "
        "print(sorted(m for m in ('ase', 'scipy') if m in sys.modules))"
    )
    run = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    )
    assert run.stdout.strip() == "[]"
