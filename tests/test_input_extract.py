"""core/qe/input_extract.py: the extract strip's chips (spec 11 R5)."""

import pytest

from qe_studio.core.qe.input_extract import Chip, clean, extract
from qe_studio.core.qe.input_lint import lint

from conftest import FIXTURES


def chips(text: str) -> dict[str, Chip]:
    return {chip.label: chip for chip in extract(lint(text))}


def read(rel: str) -> dict[str, Chip]:
    return chips((FIXTURES / rel).read_text())


def test_al_scf_extract_matches_the_file():
    got = read("al_bands/al.scf.in")
    assert got["calculation"] == Chip("calculation", "scf", 2)
    assert got["prefix"].value == "al"
    assert got["ecutwfc"].value == "100" and got["ecutwfc"].line == 12
    assert got["ecutrho"].value == "143"
    assert got["nat"] == Chip("nat", "1", 11) and got["ntyp"].value == "1"
    assert got["occupations"].value == "smearing" and got["smearing"].value == "gaussian"
    assert got["degauss"].value == "0.01"
    assert got["conv_thr"].value == "1.0d-8"
    assert got["pseudo_dir"].value == "/home/m/Documentos/pseudo"
    assert got["K_POINTS"] == Chip("K_POINTS", "automatic 10×10×10 (0 0 0)", 29)


def test_chips_come_in_a_fixed_order():
    labels = [c.label for c in extract(lint((FIXTURES / "al_bands/al.scf.in").read_text()))]
    assert labels == [
        "calculation", "prefix", "ecutwfc", "ecutrho", "K_POINTS", "nat", "ntyp", "nspin",
        "occupations", "smearing", "degauss", "conv_thr", "pseudo_dir",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("card", "value"),
    [
        ("K_POINTS automatic\n8 8 8 0 0 0", "automatic 8×8×8 (0 0 0)"),
        ("K_POINTS {automatic}\n4 4 4 1 1 1", "automatic 4×4×4 (1 1 1)"),
        ("K_POINTS automatic\n6 6 6", "automatic 6×6×6"),
        ("K_POINTS gamma", "gamma"),
        ("K_POINTS {crystal_b}\n5\n0 0 0 20\n", "crystal_b 5 pontos"),
        ("K_POINTS\n60\n0 0 0 1\n", "tpiba 60 pontos"),
        ("K_POINTS automatic", "automatic"),  # nothing under the card: no grid to show
    ],
)
def test_k_points_chip(card, value):
    assert chips(f"&control\n/\n{card}\n")["K_POINTS"].value == value


def test_absent_parameters_show_known_defaults_dimmed():
    got = chips("&control\n prefix = 'x'\n/\n&system\n nat = 2\n/\n")
    calc = got["calculation"]
    assert (calc.value, calc.is_default, calc.line) == ("scf", True, 1)  # line of &control
    assert calc.text == "calculation: scf (padrão)"
    assert (got["nspin"].value, got["nspin"].is_default) == ("1", True)
    assert (got["occupations"].value, got["occupations"].is_default) == ("fixed", True)
    assert not got["nat"].is_default
    assert "ecutwfc" not in got and "conv_thr" not in got  # no default worth inventing


def test_defaults_without_their_namelist_have_nowhere_to_go():
    got = chips("&system\n nat = 2\n/\n")
    assert got["calculation"].line is None


@pytest.mark.parametrize(
    ("system", "value"),
    [
        (" nspin = 2", "2"),
        (" noncolin = .true.", "não colinear"),
        (" noncolin = .true., lspinorb = .true.", "SO"),
        (" noncolin = .false., nspin = 2", "2"),
        (" lspinorb = .true.", "1"),  # spin-orbit needs noncolin: nspin stays
    ],
)
def test_spin_chip(system, value):
    assert chips(f"&system\n{system}\n/\n")["nspin"].value == value


def test_extract_of_a_broken_input():
    text = "&control\n calculation = 'relax'\n prefix = 'si\n&system\n ecutwfc = 30\n/\n"
    got = chips(text)  # &control never closed, the quote never closed
    assert got["calculation"].value == "relax"
    assert got["ecutwfc"].value == "30"


def test_repeated_namelist_reads_the_first_one():
    got = chips("&control\n calculation = 'scf'\n/\n&control\n calculation = 'nscf'\n/\n")
    assert got["calculation"].value == "scf"


@pytest.mark.parametrize(
    ("rel", "labels"),
    [
        ("al_bands/bands.in", ["filband", "lsym"]),
        ("ni_pdos_spin/ni.pdos.in", ["degauss", "DeltaE", "Emin", "Emax"]),
    ],
)
def test_other_programs(rel, labels):
    assert [c.label for c in extract(lint((FIXTURES / rel).read_text()))] == labels


def test_projwfc_values():
    got = read("ni_pdos_spin/ni.pdos.in")
    assert (got["Emin"].value, got["Emax"].value, got["DeltaE"].value) == ("5.0", "25.0", "0.1")
    assert got["degauss"].value == "0.02"


def test_dos_and_bands_spin_component():
    got = chips("&dos\n fildos = 'out.dos', Emin = -5, DeltaE = 0.01\n/\n")
    assert [c.label for c in got.values()] == ["fildos", "DeltaE", "Emin"]
    assert got["fildos"].value == "out.dos"
    bands = chips("&bands\n prefix='x', filband='b', spin_component=2, lsym=.true.\n/\n")
    assert [c.value for c in bands.values()] == ["b", "2", ".true."]


def test_unrecognized_programs_have_no_chips():
    assert extract(lint("&inputph\n tr2_ph = 1d-14\n/\n")) == ()
    assert extract(lint("")) == ()


def test_clean_strips_one_pair_of_quotes():
    assert clean(" 'si' ") == "si"
    assert clean('"a b"') == "a b"
    assert clean("'x") == "'x"
    assert clean("1.0, 2.0") == "1.0, 2.0"
