"""Spec 40 R2: the structures of the surface types without pymatgen (model, elements, geometry, the
cell card, writing a structure, the molecule)."""

from __future__ import annotations

import numpy as np
import pytest

from fragment_helpers import SMALL
from qe_studio.core.calc_create.surface import SurfaceError
from qe_studio.core.calc_create.surface.elements import covalent_radius, element_of
from qe_studio.core.calc_create.surface.geometry import (
    interplanar,
    min_image,
    pair_images,
    vacuum_gaps,
)
from qe_studio.core.calc_create.surface.model import Model, flags_of, model_of, species_rows
from qe_studio.core.calc_create.surface.molecule import molecule_of
from qe_studio.core.calc_create.surface.write import CONSTRAINTS, HUBBARD_V, put_structure
from qe_studio.core.qe.cell_card import set_cell
from qe_studio.core.qe.input_edit import InputEditor
from qe_studio.core.qe.lattice import BOHR_ANGSTROM

from calc_helpers import AL_SCF, from_text
from surface_helpers import BULK, MOLECULE, SLAB_001, SLAB_010, SUPERCELL_001, read


# -- vacuum gaps --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("path", "gaps"),
    [
        (BULK, (0.80, 1.02, 1.85)),
        (SLAB_001, (0.72, 1.04, 15.07)),
        (SLAB_010, (0.84, 1.79, 15.25)),
        (SUPERCELL_001, (0.72, 1.04, 15.07)),
        (MOLECULE, (19.34, 19.58, 18.57)),
    ],
    ids=lambda value: getattr(value, "name", ""),
)
def test_vacuum_gaps_of_the_reference_scfs(path, gaps):
    crystal = read(path).crystal
    assert np.allclose(vacuum_gaps(crystal.cell, crystal.frac), gaps, atol=0.01)


def test_a_slab_wrapped_around_the_edge_has_its_gap_in_the_middle():
    cell = np.diag([4.0, 5.0, 10.0])
    frac = np.array([[0, 0, 0.95], [0.5, 0.5, 0.0], [0, 0.5, 0.05]])
    assert vacuum_gaps(cell, frac)[2] == pytest.approx(9.0)


def test_one_atom_leaves_the_whole_cell_empty():
    cell = np.array([[3.0, 0, 0], [1.0, 3.0, 0], [0, 0, 7.0]])
    assert np.allclose(vacuum_gaps(cell, np.zeros((1, 3))), interplanar(cell))
    assert interplanar(cell)[2] == pytest.approx(7.0)


def test_minimum_images_keep_the_image_of_the_fractions_as_written():
    cell = np.diag([10.0, 10.0, 10.0])
    distance, image = min_image(np.array([0.0, 0.0, 0.9]), cell)
    assert distance == pytest.approx(1.0) and image.tolist() == [0, 0, -1]
    frac = np.array([[0, 0, 0.95], [0, 0, 0.05]])
    distances, images = pair_images(frac, cell, [0], [1])
    assert distances[0, 0] == pytest.approx(1.0) and images[0, 0].tolist() == [0, 0, 1]


# -- elements -----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("label", "element"),
    [("Fe1", "Fe"), ("Fe_up", "Fe"), ("Hg", "Hg"), ("C2", "C"), ("Co", "Co"), ("H", "H")],
)
def test_element_of_a_label(label, element):
    assert element_of(label) == element


def test_a_label_without_element_is_an_error():
    with pytest.raises(SurfaceError, match="Espécie sem elemento conhecido: Qq"):
        element_of("Qq")


def test_covalent_radii_are_the_scripts():
    assert [covalent_radius(label) for label in ("H", "O", "Al", "Si")] == [0.31, 0.66, 1.21, 1.11]


# -- model --------------------------------------------------------------------------------------------
def test_model_of_reads_the_flags_as_written():
    model = model_of(read(SLAB_001))
    assert len(model) == 34 and len(model.flags) == 34
    assert sum(flag == (0, 0, 0) for flag in model.flags) == 14
    assert model_of(read(BULK)).flags == (None,) * 34


def test_model_of_an_unreadable_structure_is_an_error():
    scf = from_text(AL_SCF.read_text().replace("ibrav=  2", "ibrav=  99"))
    with pytest.raises(SurfaceError, match="ilegível"):
        model_of(scf)


def test_flags_and_species_rows():
    text = "&SYSTEM\n nat = 2, ntyp = 1\n/\nATOMIC_SPECIES\nO 16 O.UPF ! oxygen\nH 1 H.UPF\n"
    text += "ATOMIC_POSITIONS crystal\nO 0 0 0 1 0 1 ! keep\nO 0.5 0 0\nO 9 9 9 0 0 0\n"
    assert flags_of(text) == ((1, 0, 1), None)
    assert species_rows(text) == ["O 16 O.UPF ! oxygen"]


# -- the cell card ------------------------------------------------------------------------------------
def test_set_cell_replaces_a_bravais_lattice():
    editor = InputEditor.from_text(AL_SCF.read_text())
    note = set_cell(editor, "angstrom", ["4 0 0", "0 4 0", "0 0 4"])
    assert note == "ibrav = 2 trocado por 0: a célula vai em CELL_PARAMETERS"
    assert editor.get("system", "ibrav") == "0"
    assert not any(key.startswith("celldm") for key in editor.keys("system"))
    assert editor.card("CELL_PARAMETERS").lines == ("4 0 0", "0 4 0", "0 0 4")


# -- writing a structure ------------------------------------------------------------------------------
def al_model() -> Model:
    cell = np.diag([4.0, 4.0, 14.0])
    frac = np.array([[0.0, 0.0, 0.5], [0.5, 0.5, 0.5]])
    return Model(cell, ("Al", "Al"), frac, ((0, 0, 0), None))


def test_put_structure_in_an_ibrav_2_scf():
    editor = InputEditor.from_text(AL_SCF.read_text())
    notes = put_structure(editor, al_model(), species_rows(AL_SCF.read_text()))
    assert notes == ["ibrav = 2 trocado por 0: a célula vai em CELL_PARAMETERS"]
    text = editor.text()
    assert editor.get("system", "ibrav") == "0" and "celldm" not in text
    assert editor.get("system", "nat") == "2" and editor.get("system", "ntyp") == "1"
    positions = editor.card("ATOMIC_POSITIONS")
    assert positions.option == "crystal"
    assert positions.lines[0].split()[:4] == ["Al", "0.0000000000", "0.0000000000", "0.5000000000"]
    assert positions.lines[0].endswith("   0 0 0") and len(positions.lines[1].split()) == 4
    assert editor.card("CELL_PARAMETERS").option == "angstrom"
    assert "ecutwfc = 100," in text  # the rest as written
    crystal = from_text(text.replace("ibrav=  0", "ibrav = 0")).crystal
    assert np.allclose(crystal.cell, al_model().cell)


def test_per_atom_cards_go_with_a_note():
    text = AL_SCF.read_text() + "\nATOMIC_FORCES\nAl 0.1 0 0\n"
    editor = InputEditor.from_text(text)
    notes = put_structure(editor, al_model(), species_rows(text))
    assert "ATOMIC_FORCES removido: os átomos mudaram" in notes
    assert editor.card("ATOMIC_FORCES") is None


def test_unused_species_leave_and_their_keys_follow():
    text = AL_SCF.read_text().replace("ntyp= 1,", "ntyp= 2, starting_magnetization(2) = 0.5,")
    text = text.replace("ATOMIC_SPECIES\n", "ATOMIC_SPECIES\n H 1.0 H.UPF\n")
    editor = InputEditor.from_text(text)
    notes = put_structure(editor, al_model(), species_rows(text))
    assert editor.card("ATOMIC_SPECIES").lines == ("Al 26.981539 Al.pbe-n-rrkjus_psl.1.0.0.UPF",)
    assert editor.get("system", "ntyp") == "1"
    assert editor.get("system", "starting_magnetization(1)") == "0.5"
    assert any("removidas de ATOMIC_SPECIES: H" in note for note in notes)


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (AL_SCF.read_text() + "\nCONSTRAINTS\n1\n'distance' 1 2 2.0\n", CONSTRAINTS),
        (SMALL, HUBBARD_V),
    ],
    ids=["constraints", "hubbard_v"],
)
def test_cards_that_number_atoms_are_errors(text, error):
    editor = InputEditor.from_text(text)
    with pytest.raises(SurfaceError, match=error):
        put_structure(editor, al_model(), species_rows(text))
    assert editor.text() == text  # refused before any edit


def test_a_species_without_its_row_is_an_error():
    model = al_model().replace(labels=("Al", "Si"))
    editor = InputEditor.from_text(AL_SCF.read_text())
    with pytest.raises(SurfaceError, match="Espécie sem linha em ATOMIC_SPECIES: Si"):
        put_structure(editor, model, ["Al 27 Al.UPF"])
    assert editor.text() == AL_SCF.read_text()


# -- the molecule -------------------------------------------------------------------------------------
SCF_POSITIONS = np.array(
    [
        [0.0000000000, -0.0003231852, -0.1400020799],
        [0.0000000000, 0.0001734786, 2.1763925830],
        [0.0000000000, 1.0579050981, 2.4579796997],
        [0.9160061468, -0.5288776958, 2.4578148986],
        [-0.9160061468, -0.5288776958, 2.4578148986],
    ]
)


def test_the_molecule_of_the_reference_scf():
    molecule = molecule_of(read(MOLECULE))
    assert molecule.labels == ("Hg", "C", "H", "H", "H") and molecule.anchor == 0
    assert not molecule.rotated
    assert molecule.extent == pytest.approx(2.60, abs=0.01)
    assert np.allclose(molecule.coords, SCF_POSITIONS - SCF_POSITIONS[0], atol=1e-9)


def lying_molecule_text(shift: float) -> str:
    """The reference molecule turned onto +x and moved so the box edge cuts it (a cube of 40 Bohr)."""
    turned = SCF_POSITIONS[:, [2, 1, 0]] * [1, 1, -1]  # z → x
    box = 40 * BOHR_ANGSTROM
    turned = (turned + [shift, 5.0, 5.0]) % box
    rows = "\n".join(
        f"{label} {x:.10f} {y:.10f} {z:.10f}"
        for label, (x, y, z) in zip(("Hg", "C", "H", "H", "H"), turned, strict=True)
    )
    text = MOLECULE.read_text()
    head = text[: text.index("ATOMIC_POSITIONS")]
    return f"{head}ATOMIC_POSITIONS (angstrom)\n{rows}\n\nK_POINTS gamma\n"


def test_a_lying_molecule_cut_by_the_box_comes_out_whole_and_upright():
    scf = from_text(lying_molecule_text(shift=-1.0))
    frac_x = scf.crystal.frac[:, 0]
    assert frac_x.min() < 0.1 and frac_x.max() > 0.9  # the edge cuts it
    molecule = molecule_of(scf)
    assert molecule.rotated
    upright = molecule_of(read(MOLECULE))
    axis = molecule.coords[1] / np.linalg.norm(molecule.coords[1])
    assert axis[2] == pytest.approx(1.0)
    assert molecule.extent == pytest.approx(upright.extent, abs=0.01)
    pairs = np.linalg.norm(molecule.coords[:, None] - molecule.coords[None], axis=-1)
    reference = np.linalg.norm(upright.coords[:, None] - upright.coords[None], axis=-1)
    assert np.allclose(pairs, reference, atol=1e-6)  # whole: no atom left across the edge


def test_an_anchor_out_of_the_molecule_is_an_error():
    with pytest.raises(SurfaceError, match="fora da molécula"):
        molecule_of(read(MOLECULE), anchor=6)
