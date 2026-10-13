from pathlib import Path

import numpy as np
import pytest
from helpers import h3chg_input

from viewer3d.core.example import SI_DIAMOND_INPUT
from viewer3d.core.lattice import BOHR
from viewer3d.core.qe_input import parse_input, read_structure
from viewer3d.core.structure import StructureError

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def ok(text):
    result = parse_input(text)
    assert not isinstance(result, StructureError), result
    return result


def err(text):
    result = parse_input(text)
    assert isinstance(result, StructureError)
    assert result.message
    return result.message


def make(system="ibrav = 1, celldm(1) = 10.0, nat = 1, ntyp = 1", tail=None, control=""):
    if tail is None:
        tail = "ATOMIC_SPECIES\nSi 28.0 Si.UPF\nATOMIC_POSITIONS (alat)\nSi 0.0 0.0 0.0\n"
    return f"&CONTROL\n{control}\n/\n&SYSTEM\n{system}\n/\n{tail}"


# ---------------------------------------------------------------- reference structures


def test_si_diamond():
    s = ok(SI_DIAMOND_INPUT)
    expected = 5.39760755 / 2 * np.array([[-1, 0, 1], [0, 1, 1], [-1, 1, 0]])
    assert s.cell == pytest.approx(expected, abs=1e-6)
    assert len(s) == 2
    d = np.linalg.norm(s.cart[1] - s.cart[0])
    assert d == pytest.approx(2.3372, abs=1e-3)
    assert s.formula == "Si2"
    assert s.source.ibrav == 2
    assert s.source.prefix == "si"
    assert s.source.alat_bohr == pytest.approx(10.2)
    assert s.source.warnings == ()


def test_h3chg_molecule():
    s = ok(h3chg_input())
    assert s.cell == pytest.approx(21.16709 * np.eye(3), abs=1e-4)
    cart = s.cart
    assert np.linalg.norm(cart[0] - cart[1]) == pytest.approx(2.316, abs=2e-3)
    assert np.linalg.norm(cart[1] - cart[2]) == pytest.approx(1.09, abs=1e-3)
    assert s.formula == "CH3Hg"


def test_sample_scf_in():
    s = ok((SAMPLES / "scf.in").read_text())
    assert len(s) == 72
    assert s.formula == "CH18Al8HgO36Si8"
    assert s.source.ibrav == 0 and s.source.nat == 72 and s.source.ntyp == 6
    assert s.source.prefix == "kaolinite-slab-001-2x1x1-silicon-O49"
    assert s.cell[0] == pytest.approx([10.37905170281884, 0, 0])
    assert s.source.alat_bohr == pytest.approx(10.37905170281884 / BOHR)
    assert [x.label for x in s.species] == ["Al", "Si", "O", "H", "Hg", "C"]
    assert s.species[4].mass == pytest.approx(200.59)
    assert s.flags[0] is None and s.flags[8] == (0, 0, 0) and s.flags[40] is None
    assert s.frac[0] == pytest.approx([0.1469557035, 0.5021653986, 0.5297838877])
    assert s.frac[:, 0].min() < 0  # coordinates outside [0, 1) are kept as written
    assert s.source.warnings == ()


# ---------------------------------------------------------------- tolerant namelists


def test_space_before_namelist_header_and_slash_on_own_line():
    s = ok(
        "  &control\n    calculation='scf'\n  /\n   &system\n ibrav=1\n celldm(1)=10\n nat=1\n  /\n"
        "ATOMIC_POSITIONS alat\nSi 0 0 0\n"
    )
    assert s.source.calculation == "scf"


def test_system_header_glued_to_keys_on_same_line():
    s = ok(
        "&control\n/\n&system ibrav=1, celldm(1)=10.0, nat=1 /\nATOMIC_POSITIONS alat\nSi 0 0 0\n"
    )
    assert s.source.nat == 1


def test_keys_on_separate_lines_without_commas():
    s = ok(make(system="ibrav = 1\ncelldm(1) = 10.0\nnat = 1\nntyp = 1\n"))
    assert s.source.ibrav == 1 and s.source.nat == 1


def test_trailing_commas_and_several_keys_per_line():
    s = ok(make(system="ibrav=1, celldm(1)=10.0, nat=1,\nntyp=1,"))
    assert s.source.ntyp == 1
    s = ok(make(system="ibrav=1 celldm(1)=10.0 nat=1 ntyp=1"))
    assert s.source.nat == 1


def test_blank_lines_and_comments_inside_namelist():
    s = ok(make(system="ibrav = 1\n\n  ! a comment line\ncelldm(1) = 10.0 ! trailing\n\nnat = 1\n"))
    assert s.source.celldm[0] == 10.0


def test_keys_are_case_insensitive():
    s = ok(make(system="IBRAV=1, Celldm(1)=10.0, NAT=1, NTYP=1"))
    assert s.source.celldm[0] == 10.0


def test_quoted_values_and_equals_inside_quotes():
    s = ok(make(control="prefix = \"my=run\"\ncalculation='relax'"))
    assert s.source.prefix == "my=run"
    assert s.source.calculation == "relax"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1.0D1", 10.0),
        ("1.d1", 10.0),
        ("10.d0", 10.0),
        ("1e1", 10.0),
        ("10", 10.0),
        ("10.0_dp", 10.0),
    ],
)
def test_fortran_number_forms(text, value):
    s = ok(make(system=f"ibrav=1, celldm(1)={text}, nat=1"))
    assert s.source.celldm[0] == value


def test_leading_dot_number_in_positions():
    s = ok(make(tail="ATOMIC_POSITIONS crystal\nSi .5 .25 -.5\n"))
    assert s.frac[0] == pytest.approx([0.5, 0.25, -0.5])


def test_namelist_key_named_like_a_card():
    s = ok(make(system="ibrav=1, celldm(1)=10.0, nat=1\noccupations = 'smearing'\nconstraints=1"))
    assert s.source.nat == 1


def test_abc_parameters_in_angstrom():
    s = ok(make(system="ibrav=14, A=5.0, B=6.0, C=7.0, cosAB=0.0, cosAC=0.0, cosBC=0.0, nat=1"))
    assert np.linalg.norm(s.cell, axis=1) == pytest.approx([5.0, 6.0, 7.0])
    s = ok(make(system="ibrav=1, a=5.5, nat=1"))
    assert s.cell == pytest.approx(5.5 * np.eye(3))
    assert s.source.celldm[0] == pytest.approx(5.5 / BOHR)


def test_cos_parameters_for_monoclinic():
    s = ok(make(system="ibrav=12, A=5.0, B=6.0, C=7.0, cosAB=0.5, nat=1"))
    cosab = s.cell[0] @ s.cell[1] / (5.0 * 6.0)
    assert cosab == pytest.approx(0.5)


# ---------------------------------------------------------------- cards


def test_cards_any_case_and_option_forms():
    for option in ("(angstrom)", "{angstrom}", "angstrom", "( angstrom )", "{ANGSTROM}"):
        tail = f"atomic_species\nSi 28.0 Si.UPF\nAtomic_Positions {option}\nSi 1.0 2.0 3.0\n"
        s = ok(make(system="ibrav=1, celldm(1)=10.0, nat=1", tail=tail))
        assert s.cart[0] == pytest.approx([1.0, 2.0, 3.0])


def test_card_ends_at_next_card_or_eof_and_k_points_ignored():
    tail = (
        "K_POINTS automatic\n4 4 4 1 1 1\n\n"
        "ATOMIC_POSITIONS crystal\nSi 0.1 0.2 0.3\nK_POINTS gamma\n"
    )
    s = ok(make(tail=tail))
    assert len(s) == 1
    s = ok(make(tail="ATOMIC_POSITIONS crystal\nSi 0.1 0.2 0.3\nK_POINTS gamma"))
    assert s.frac[0] == pytest.approx([0.1, 0.2, 0.3])


def test_hash_comments_in_cards():
    tail = (
        "ATOMIC_SPECIES\n# species\nSi 28.0 Si.UPF # pseudo\n"
        "ATOMIC_POSITIONS crystal\n# pos\nSi 0 0 0 ! x\n"
    )
    s = ok(make(tail=tail))
    assert s.species[0].pseudo == "Si.UPF"


def test_positions_units_are_equivalent():
    base = "ibrav=1, celldm(1)=10.0, nat=1"
    alat = ok(make(system=base, tail="ATOMIC_POSITIONS alat\nSi 0.1 0.2 0.3\n"))
    bohr = ok(make(system=base, tail="ATOMIC_POSITIONS bohr\nSi 1.0 2.0 3.0\n"))
    ang = ok(
        make(system=base, tail=f"ATOMIC_POSITIONS angstrom\nSi {BOHR} {2 * BOHR} {3 * BOHR}\n")
    )
    cry = ok(make(system=base, tail="ATOMIC_POSITIONS crystal\nSi 0.1 0.2 0.3\n"))
    for other in (bohr, ang, cry):
        assert other.frac == pytest.approx(alat.frac)
        assert other.cart == pytest.approx(alat.cart)


def test_positions_without_unit_default_to_alat_with_warning():
    s = ok(make(tail="ATOMIC_POSITIONS\nSi 0.1 0.2 0.3\n"))
    assert s.frac[0] == pytest.approx([0.1, 0.2, 0.3])
    assert any("alat" in w for w in s.source.warnings)


def test_ibrav0_units_give_same_structure():
    alat = 8.0
    vec = np.array([[1.0, 0.0, 0.0], [0.2, 1.1, 0.0], [0.0, 0.3, 1.5]])
    pos = np.array([[0.1, 0.2, 0.3], [0.5, 0.5, 0.5]])

    def text(unit_line, vectors, extra_system=""):
        rows = "\n".join(" ".join(f"{x:.12f}" for x in v) for v in vectors)
        atoms = "\n".join("Si " + " ".join(f"{x:.12f}" for x in p) for p in pos)
        return (
            f"&SYSTEM\nibrav=0, nat=2 {extra_system}\n/\nATOMIC_SPECIES\nSi 28 x.UPF\n"
            f"CELL_PARAMETERS {unit_line}\n{rows}\nATOMIC_POSITIONS alat\n{atoms}\n"
        )

    # |a1| = alat in every form, so positions in alat units are identical
    a = ok(text("alat", vec, f", celldm(1)={alat}"))
    b = ok(text("bohr", vec * alat))
    c = ok(text("angstrom", vec * alat * BOHR))
    d = ok(text(f"(alat= {alat})", vec))
    for other in (b, c, d):
        assert other.cell == pytest.approx(a.cell)
        assert other.frac == pytest.approx(a.frac)
        assert other.source.alat_bohr == pytest.approx(alat)
    assert a.cell[0] == pytest.approx([alat * BOHR, 0, 0])


def test_ibrav0_alat_option_without_value_uses_celldm():
    text = (
        "&SYSTEM\nibrav=0, nat=1, celldm(1)=5.0\n/\nCELL_PARAMETERS {alat}\n"
        "1 0 0\n0 1 0\n0 0 1\nATOMIC_POSITIONS crystal\nSi 0 0 0\n"
    )
    assert ok(text).cell == pytest.approx(5.0 * BOHR * np.eye(3))


# ---------------------------------------------------------------- per-atom and species data


def test_if_pos_present_absent_and_incomplete():
    tail = (
        "ATOMIC_SPECIES\nSi 28 x\nATOMIC_POSITIONS crystal\nSi 0 0 0 0 1 0\nSi 0.1 0.1 0.1\n"
        "Si 0.2 0.2 0.2 1 1\n"
    )
    s = ok(make(system="ibrav=1, celldm(1)=10, nat=3", tail=tail))
    assert s.flags == ((0, 1, 0), None, None)
    assert any("if_pos" in w for w in s.source.warnings)


def test_exactly_nat_lines_are_atoms():
    tail = "ATOMIC_POSITIONS crystal\nSi 0 0 0\nSi 0.1 0.1 0.1\nSi 0.2 0.2 0.2\n"
    s = ok(make(system="ibrav=1, celldm(1)=10, nat=2", tail=tail))
    assert len(s) == 2
    assert any("nat" in w for w in s.source.warnings)


def test_species_labels_to_elements():
    tail = (
        "ATOMIC_SPECIES\nFe1 55.8 a.UPF\nFe_up 55.8 b.UPF\nC2 12 c.UPF\nH_ads 1 d.UPF\nX 1 e\n"
        "ATOMIC_POSITIONS crystal\nFe1 0 0 0\nFe_up .1 0 0\nC2 .2 0 0\nH_ads .3 0 0\nX .4 0 0\n"
    )
    s = ok(make(system="ibrav=1, celldm(1)=10, nat=5, ntyp=5", tail=tail))
    assert s.symbols[:4] == ("Fe", "Fe", "C", "H")
    assert s.species_index.tolist() == [0, 1, 2, 3, 4]
    assert any("'X'" in w for w in s.source.warnings)


def test_starting_magnetization_hubbard_and_nspin():
    system = (
        "ibrav=1, celldm(1)=10, nat=1, ntyp=2, nspin=2, starting_magnetization(1)=0.5,\n"
        "Hubbard_U(2) = 4.5, STARTING_MAGNETIZATION(2) = -.3"
    )
    s = ok(make(system=system))
    assert s.source.nspin == 2
    assert s.source.starting_magnetization == {1: 0.5, 2: -0.3}
    assert s.source.hubbard_u == {2: 4.5}


def test_hubbard_card_warning():
    s = ok(make(tail="ATOMIC_POSITIONS crystal\nSi 0 0 0\nHUBBARD (ortho-atomic)\nU Si-3d 4.0\n"))
    assert any("HUBBARD" in w for w in s.source.warnings)


def test_missing_atomic_species_is_tolerated():
    s = ok(make(tail="ATOMIC_POSITIONS crystal\nSi 0 0 0\n"))
    assert s.species[0].label == "Si" and s.species[0].mass is None
    assert any("ATOMIC_SPECIES" in w for w in s.source.warnings)


# ---------------------------------------------------------------- errors, in Portuguese


def test_error_messages():
    assert "ibrav ausente ou inválido" in err(make(system="celldm(1)=10, nat=1"))
    assert "ibrav ausente ou inválido" in err(make(system="ibrav=abc, celldm(1)=10, nat=1"))
    assert "ibrav = 99" in err(make(system="ibrav=99, celldm(1)=10, nat=1"))
    assert "sem ATOMIC_POSITIONS" in err(make(tail="ATOMIC_SPECIES\nSi 28 x\n"))
    assert "nat = 5, mas ATOMIC_POSITIONS tem 3 linhas" in err(
        make(
            system="ibrav=1, celldm(1)=10, nat=5",
            tail="ATOMIC_POSITIONS crystal\nSi 0 0 0\nSi 0 0 0\nSi 0 0 0\n",
        )
    )
    assert "crystal_sg" in err(make(tail="ATOMIC_POSITIONS crystal_sg\nSi 0 0 0\n"))
    assert "nat" in err(make(system="ibrav=1, celldm(1)=10"))
    assert "celldm(1)" in err(make(system="ibrav=1, nat=1"))
    assert "CELL_PARAMETERS" in err(make(system="ibrav=0, nat=1"))
    assert "&SYSTEM" in err("&control\n/\n")
    assert "linha" in err(make(tail="ATOMIC_POSITIONS crystal\nSi 0 zero 0\n"))
    assert "volume" in err(
        "&SYSTEM\nibrav=0, nat=1\n/\nCELL_PARAMETERS bohr\n1 0 0\n2 0 0\n0 0 1\n"
        "ATOMIC_POSITIONS crystal\nSi 0 0 0\n"
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n\n",
        "&&&&",
        "\x00\x01\x02",
        "/\n/\n&SYSTEM",
        "ATOMIC_POSITIONS",
        "&system\nibrav=1\ncelldm(1)=\n/\n",
        "&system ibrav = ' unterminated",
    ],
)
def test_garbage_never_raises(text):
    assert isinstance(parse_input(text), StructureError)


def test_read_structure_file_errors(tmp_path):
    missing = read_structure(tmp_path / "nope.in")
    assert isinstance(missing, StructureError) and "não encontrado" in missing.message
    empty = tmp_path / "empty.in"
    empty.write_text("")
    assert "vazio" in read_structure(empty).message
    binary = tmp_path / "bin.in"
    binary.write_bytes(bytes(range(256)))
    assert isinstance(read_structure(binary), StructureError)
    assert isinstance(read_structure(tmp_path), StructureError)  # a directory


def test_read_structure_records_path(tmp_path):
    f = tmp_path / "si.in"
    f.write_text(SI_DIAMOND_INPUT)
    s = read_structure(f)
    assert s.source.path == str(f)
