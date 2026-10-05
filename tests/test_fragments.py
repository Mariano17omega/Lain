"""Spec 30 R2: the atoms of an SCF as written and the two fragments (clean / isolated) made from it."""

import pytest

from fragment_helpers import SMALL, changes, lint_errors, slab_scf
from qe_studio.core.calc_create.fragments import (
    CLEAN,
    ISOLATED,
    atom_rows,
    split_input,
)
from qe_studio.core.qe.input_edit import InputEditor


def editor_of(text: str) -> InputEditor:
    editor = InputEditor.from_text(text)
    assert editor.issues == []
    return editor


def species_of(text: str) -> list[str]:
    card = editor_of(text).card("ATOMIC_SPECIES")
    assert card is not None
    return [line.split()[0] for line in card.lines]


def rows_of(text: str, card: str = "ATOMIC_POSITIONS") -> list[str]:
    rows = editor_of(text).card_rows(card)
    assert rows is not None
    return rows


# -- atom_rows -----------------------------------------------------------------------------------
def test_the_rows_are_the_atoms_as_written():
    atoms = atom_rows(SMALL)
    assert (atoms.unit, atoms.error, len(atoms.rows)) == ("angstrom", "", 6)
    assert [(a.index, a.label) for a in atoms.rows] == [
        (1, "Fe"),
        (2, "Fe"),
        (3, "O"),
        (4, "O"),
        (5, "H"),
        (6, "H"),
    ]
    assert (atoms.rows[4].x, atoms.rows[4].y, atoms.rows[4].z) == ("1.5", "1.5", "1.5")
    slab = atom_rows(slab_scf())
    assert slab.unit == "crystal" and len(slab.rows) == 34
    assert slab.rows[0].x == "0.2971900999"  # not rounded: what goes to the file


def test_rows_without_a_structure_the_app_can_build():
    # No CELL_PARAMETERS: ScfInfo.crystal would be None, the atoms are still listed.
    no_cell = SMALL.replace("CELL_PARAMETERS angstrom\n10 0 0\n0 10 0\n0 0 10\n", "")
    assert len(atom_rows(no_cell).rows) == 6
    no_nat = SMALL.replace("  nat = 6\n", "")
    assert len(atom_rows(no_nat).rows) == 6  # every row when nat is missing
    fewer = SMALL.replace("nat = 6", "nat = 3")
    assert [a.index for a in atom_rows(fewer).rows] == [1, 2, 3]  # pw.x reads nat of them


def test_a_structure_that_cannot_be_listed_says_why():
    assert atom_rows(SMALL.replace("angstrom\nFe 0", "crystal_sg\nFe 0")).error == (
        "Posições em crystal_sg não são suportadas"
    )
    assert "sem ATOMIC_POSITIONS" in atom_rows("&system\n/\n").error
    assert "nat = 9" in atom_rows(SMALL.replace("nat = 6", "nat = 9")).error
    assert "ilegível" in atom_rows(SMALL.replace("H 1.5 1.5 1.5", "H 1.5")).error
    assert atom_rows(SMALL).error == ""


# -- split: atoms, species and what is numbered by them -----------------------------------------------
def test_the_atoms_are_shared_and_each_row_keeps_its_text():
    result = split_input(SMALL, {5, 6})
    assert result.errors == ()
    clean, isolated = rows_of(result.clean), rows_of(result.isolated)
    assert len(clean) + len(isolated) == 6
    assert clean == [
        "Fe 0 0 0  0 0 0 ! slab Fe 1",  # the flags and the comment of the line
        "Fe 2 0 0",
        "O 1 1 1 ! comment",
        "O 3 1 1",
    ]
    assert isolated == ["H 1.5 1.5 1.5", "H 3.5 1.5 1.5"]
    for text, nat in ((result.clean, 4), (result.isolated, 2)):
        assert editor_of(text).get("system", "nat") == str(nat)


def test_a_species_with_no_atom_leaves_the_card_and_ntyp():
    result = split_input(SMALL, {5, 6})
    assert species_of(result.clean) == ["Fe", "O"]
    assert species_of(result.isolated) == ["H"]
    assert editor_of(result.clean).get("system", "ntyp") == "2"
    assert editor_of(result.isolated).get("system", "ntyp") == "1"
    both = split_input(SMALL, {2, 5})  # one atom of each of two species on each side
    assert species_of(both.isolated) == ["Fe", "H"]
    assert species_of(both.clean) == ["Fe", "O", "H"]
    assert editor_of(both.clean).get("system", "ntyp") == "3"  # nothing left: unchanged


def test_what_is_numbered_by_species_follows_them():
    clean = editor_of(split_input(SMALL, {5, 6}).clean)
    assert clean.keys("system").count("starting_magnetization(1)") == 1
    assert clean.get("system", "starting_magnetization(1)") == "0.5"
    assert clean.get("system", "starting_magnetization(2)") == "0.0"
    assert clean.get("system", "starting_magnetization(3)") is None  # H left
    assert clean.get("system", "starting_ns_eigenvalue(1,1,3)") is None
    isolated_text = split_input(SMALL, {5, 6}).isolated
    isolated = editor_of(isolated_text)
    assert isolated.get("system", "starting_magnetization(1)") == "0.2"  # H was the third
    assert isolated.get("system", "starting_ns_eigenvalue(1,1,1)") == "0.1"  # the last index
    assert "Starting_Magnetization(1) = 0.2" in isolated_text  # the case it was written in
    oxygen = editor_of(split_input(SMALL, {3, 4}).clean)  # O (the second) leaves the clean one
    assert oxygen.get("system", "starting_magnetization(1)") == "0.5"
    assert oxygen.get("system", "starting_magnetization(2)") == "0.2"  # H: 3 → 2
    assert oxygen.get("system", "starting_ns_eigenvalue(1,1,2)") == "0.1"


def test_hubbard_follows_species_and_atoms():
    clean = rows_of(split_input(SMALL, {5, 6}).clean, "HUBBARD")
    assert (
        clean
        == [  # H holds no line; Fe and O stay as they are
            "U Fe-3d 5.0",
            "U O-2p 1.0",
            "V Fe-3d Fe-3d 1 2 0.2",
            "V Fe-3d O-2p 1 3 0.5",
            "V Fe-3d O-2p 2 4 0.3",
            "V Fe-3d O-2p 2 7 0.1 ! an image: atom 3 of the next cell (9 = 3 + 6), as species_keys assumes",  # 3 + 4 atoms · 1 cell
        ]
    )
    result = split_input(SMALL, {2, 5})  # clean = atoms 1, 3, 4, 6 → 1, 2, 3, 4
    assert rows_of(result.clean, "HUBBARD") == [
        "U Fe-3d 5.0",
        "U O-2p 1.0",
        "V Fe-3d O-2p 1 2 0.5",  # atoms 1, 3 → 1, 2; the others cite the atom 2, which left
    ]
    removed = [note for who, note in result.notes if who == CLEAN and "linha V removida" in note]
    assert len(removed) == 3 and "V Fe-3d Fe-3d 1 2 0.2" in removed[0]
    isolated = split_input(SMALL, {5, 6})  # Fe and O are gone: no line is left
    assert editor_of(isolated.isolated).card("HUBBARD") is None
    assert (ISOLATED, "HUBBARD sem linhas neste fragmento: o card foi removido") in isolated.notes


def test_a_card_per_atom_follows_the_atoms():
    forces = "ATOMIC_FORCES\nFe 1 0 0\nFe 2 0 0\nO 3 0 0\nO 4 0 0\nH 5 0 0\nH 6 0 0\n"
    result = split_input(SMALL + forces, {5, 6})
    assert rows_of(result.clean, "ATOMIC_FORCES") == ["Fe 1 0 0", "Fe 2 0 0", "O 3 0 0", "O 4 0 0"]
    assert rows_of(result.isolated, "ATOMIC_FORCES") == ["H 5 0 0", "H 6 0 0"]


def test_only_the_expected_lines_differ_from_the_base():
    text = slab_scf()
    atoms = atom_rows(text)
    hydrogens = {a.index for a in atoms.rows if a.label == "H"}
    result = split_input(text, hydrogens)
    assert result.errors == ()
    removed, added = changes(text, result.clean)
    assert added == ["   ntyp             = 3", "   nat              = 26"]
    positions = [a for a in atoms.rows if a.label == "H"]
    assert len(removed) == 2 + 1 + len(positions)  # ntyp, nat, the H species, the H atoms
    assert "H 1.00794 H.pbe-kjpaw_psl.1.0.0.UPF" in removed
    isolated_removed, isolated_added = changes(text, result.isolated)
    assert isolated_added == ["   ntyp             = 1", "   nat              = 8"]
    for kept in ("ecutwfc", "ecutrho", "K_POINTS automatic", "6 4 1  0 0 0", "CELL_PARAMETERS"):
        assert not any(kept in line for line in removed + isolated_removed)
    assert result.clean.count("CELL_PARAMETERS") == result.isolated.count("CELL_PARAMETERS") == 1
    for line in text.splitlines():  # a kept atom keeps its flags and its spacing
        if line.startswith("Si ") and line.rstrip().endswith("0 0 0"):
            assert line in result.clean.splitlines()
            assert line not in result.isolated.splitlines()


def test_both_fragments_lint_clean():
    for text in (SMALL, slab_scf()):
        atoms = atom_rows(text).rows
        for chosen in ({1}, {len(atoms)}, {a.index for a in atoms if a.label == "O"}):
            result = split_input(text, chosen)
            assert result.errors == ()
            assert lint_errors(result.clean) == lint_errors(text) == []
            assert lint_errors(result.isolated) == []


def test_each_species_keeps_its_relative_order():
    text = slab_scf()
    result = split_input(text, {a.index for a in atom_rows(text).rows if a.label == "Si"})
    assert species_of(result.clean) == ["Al", "O", "H"]
    assert species_of(result.isolated) == ["Si"]


# -- split: errors and notes ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "selected, message",
    [
        (set(), "Selecione os átomos do fragmento isolado"),
        ({0, 7, 99}, "Selecione os átomos do fragmento isolado"),  # none of them is an atom
        ({1, 2, 3, 4, 5, 6}, "Deixe ao menos um átomo fora da seleção: o SCF clean ficaria vazio"),
    ],
)
def test_an_empty_or_total_selection_is_an_error(selected, message):
    result = split_input(SMALL, selected)
    assert result.errors == (message,)
    assert result.clean == result.isolated == SMALL  # the tabs still have something to show


def test_constraints_are_an_error():
    result = split_input(SMALL + "CONSTRAINTS\n6 0.1\n'distance' 1 2\n", {5})
    assert result.errors == ("Restrições (CONSTRAINTS) não são suportadas na diferença de carga",)


def test_a_structure_that_cannot_be_read_is_an_error():
    result = split_input(SMALL.replace("angstrom\nFe 0", "crystal_sg\nFe 0"), {1})
    assert result.errors == ("Posições em crystal_sg não são suportadas",)


def test_notes_of_each_fragment():
    result = split_input(SMALL, {5, 6})
    assert (CLEAN, "nbnd removido: o pw.x escolhe pelo número de elétrons do fragmento") in (
        result.notes
    )
    assert editor_of(result.clean).get("system", "nbnd") is None
    assert editor_of(SMALL).get("system", "nbnd") == "40"  # the base is not touched
    no_nbnd = split_input(SMALL.replace("  nbnd = 40\n", ""), {5, 6})
    assert not any("nbnd" in note for _, note in no_nbnd.notes)
    charged = split_input(
        SMALL.replace("nbnd = 40", "tot_charge = 1\n  tot_magnetization = 2"), {5}
    )
    for which in (CLEAN, ISOLATED):
        notes = [note for who, note in charged.notes if who == which]
        assert any(note.startswith("tot_charge ") for note in notes)
        assert any(note.startswith("tot_magnetization ") for note in notes)


def test_spin_without_a_magnetization_for_the_fragment_is_a_note():
    only_iron = SMALL.replace("  starting_magnetization(2) = 0.0\n", "").replace(
        "  Starting_Magnetization(3) = 0.2\n", ""
    )
    result = split_input(only_iron, {5, 6})  # the H fragment has none; the Fe / O one has Fe's
    assert [who for who, note in result.notes if "starting_magnetization" in note] == [ISOLATED]
    no_spin = split_input(SMALL.replace("nspin = 2", "nspin = 1"), {5, 6})
    assert not any("starting_magnetization" in note for _, note in no_spin.notes)


def test_hubbard_v_with_an_old_style_key_is_not_renumbered_silently():
    old = SMALL.replace("  nbnd = 40\n", "  nbnd = 40\n  Hubbard_V(1,2,1) = 0.3\n")
    result = split_input(old, {5, 6})
    assert any("hubbard_v(1,2,1)" in note for _, note in result.notes)
