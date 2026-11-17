"""Spec 97 R3: the warnings when the energies of the equation are not comparable, and the notes."""

from pathlib import Path

import pytest

from qe_studio.core.analysis.adsorption_energy import EnergyRow, Role, read_rows
from qe_studio.core.analysis.consistency import Consistency, check, coefficients
from qe_studio.core.analysis.level_of_theory import LevelOfTheory
from qe_studio.core.qe.summary.scan import Scanner

from adsorption_helpers import (
    SI_PSEUDO_FILE,
    SI_SECOND_SITE,
    coherent_set,
    copy_scf_outputs,
    scf_paths,
    si_copy,
)
from conftest import FIXTURES, QE_EXAMPLES

ZPE = "Energia eletrônica: sem energia de ponto zero (ZPE) nem contribuição térmica."
NO_DISPERSION = (
    "Nenhuma das saídas usa correção de dispersão (vdw_corr) nem funcional vdW-DF: "
    "a fisissorção sai subestimada."
)
NOT_LINEAR = "A equação não é linear nas energias: o balanço de átomos não foi conferido."


def gamma(name: str, n: int) -> str:
    return (
        f"{name}: {n} k-pontos irredutíveis. Uma molécula isolada numa caixa grande só precisa de Γ "
        "(K_POINTS gamma)."
    )


def heads(warnings: tuple[str, ...]) -> list[str]:
    return [warning.split(":")[0] for warning in warnings]


# -- real outputs -----------------------------------------------------------------------------------
def test_a_coherent_set_has_no_warning(tmp_path):
    rows = read_rows(coherent_set(tmp_path))
    assert [(r.name, r.role) for r in rows] == [
        ("big", Role.COMPLEX),
        ("atom", Role.SUBSTRATE),
        ("small", Role.ADSORBATE),
    ]
    result = check("E_ads = E(big) - E(small) - E(atom)", rows)
    assert result.warnings == ()
    assert result.notes == (ZPE, NO_DISPERSION, gamma("small", 29))


def test_a_deprotonation_does_not_balance(tmp_path):
    rows = read_rows(coherent_set(tmp_path, big_atoms=1))
    (warning,) = check("E_ads = E(big) - E(small) - E(atom)", rows).warnings
    assert warning.startswith(
        "Os átomos não fecham: Si -1. O resultado é a energia de outra reação"
    )


@pytest.fixture
def spec78(tmp_path):
    return read_rows(scf_paths(copy_scf_outputs(tmp_path / "ads")))


def test_the_three_outputs_of_spec_78(spec78):
    result = check("E_ads = E(silicon) - E(al) - E(nifix)", spec78)
    warnings = result.warnings
    assert heads(warnings) == [
        "Os átomos não fecham",
        "Cutoffs diferentes (ecutwfc/ecutrho, Ry)",
        "Funcionais diferentes",
        "Ocupações diferentes",
        "Spin diferente",
        "Células diferentes",
        "Malhas k diferentes",
    ]  # no pseudopotential: no element in common
    assert warnings[0].startswith("Os átomos não fecham: Si +2, Al -1, Ni -1.")
    assert "25/118.918 (silicon); 100/143 (al); 30/240 (nifix)." in warnings[1]
    assert warnings[2] == "Funcionais diferentes: LDA (silicon); PBE (al, nifix)."  # by the codes
    assert (
        "sem smearing (silicon); smearing Gaussian, 0.0100 Ry (al); "
        "smearing Marzari-Vanderbilt, 0.0200 Ry (nifix)." in warnings[3]
    )
    assert "não polarizado (silicon, al); colinear (nspin=2), 0.50 μB (nifix)." in warnings[4]
    assert warnings[5].startswith("Células diferentes: complexo (silicon) e substrato (al).")
    assert warnings[6] == (
        "Malhas k diferentes: complexo (silicon: automatic 8×8×8 (0 0 0)) e "
        "substrato (al: automatic 10×10×10 (0 0 0))."
    )
    assert result.notes == (ZPE, NO_DISPERSION, gamma("nifix", 16))

    without_complex = check("E_ads = E(al) - E(nifix)", spec78).warnings
    assert heads(without_complex) == [
        "Os átomos não fecham",
        "Cutoffs diferentes (ecutwfc/ecutrho, Ry)",
        "Ocupações diferentes",
        "Spin diferente",
    ]


def test_an_equation_without_a_value_has_nothing(spec78):
    assert check("E(al) -", spec78) == Consistency((), ())
    assert check("E(xyz) - E(al)", spec78) == Consistency()


def test_a_different_pseudopotential(tmp_path):
    def other_pseudo(lines: list[str]) -> None:
        assert lines[SI_PSEUDO_FILE - 1].strip().endswith("/Si.pz-rrkj.UPF")
        lines[SI_PSEUDO_FILE - 1] = lines[SI_PSEUDO_FILE - 1].replace("pz-rrkj", "pbe-rrkj")

    rows = read_rows([si_copy(tmp_path, "x"), si_copy(tmp_path, "y", edit=other_pseudo)])
    assert check("E(x) - E(y)", rows).warnings == (
        "Pseudopotencial de Si diferente: Si.pz-rrkj.UPF (x); Si.pbe-rrkj.UPF (y).",
    )


def test_a_different_dispersion_correction(tmp_path):
    def d3(lines: list[str]) -> None:
        assert "tau(   2)" in lines[SI_SECOND_SITE - 1]
        lines.insert(SI_SECOND_SITE, "     DFT-D3 Dispersion Correction (3-body terms):\n")

    rows = read_rows([si_copy(tmp_path, "x", edit=d3), si_copy(tmp_path, "y")])
    result = check("E(x) - E(y)", rows)
    assert result.warnings == (
        "Correção de dispersão diferente: DFT-D3 (3 corpos) (x); nenhuma (y).",
    )
    assert NO_DISPERSION not in result.notes  # one of them has it: the warning says the rest
    rows = read_rows([si_copy(tmp_path, "x", edit=d3), si_copy(tmp_path, "y", edit=d3)])
    result = check("E(x) - E(y)", rows)
    assert result.warnings == () and result.notes == (ZPE,)


# -- coefficients, with rows built by hand ----------------------------------------------------------
def row(name: str, energy: float, *composition: tuple[str, int], **theory) -> EnergyRow:
    level = LevelOfTheory(composition=composition, **theory)
    return EnergyRow(Path(f"{name}.out"), name, name, 1, energy, theory=level)


@pytest.fixture
def water():
    return [
        row("h2o", -34.0, ("H", 2), ("O", 1)),
        row("h", -1.0, ("H", 1)),
        row("oh", -32.0, ("O", 1), ("H", 1)),
        row("h2", -2.3, ("H", 2)),
    ]


def test_half_a_hydrogen_molecule_balances(water):
    assert check("E(oh) + 0.5*E(h2) - E(h2o)", water).warnings == ()
    (warning,) = check("E_r = E(oh) - E(h2o)", water).warnings
    assert warning.startswith("Os átomos não fecham: H -1.")
    assert coefficients("E(oh) + 0.5*E(h2) - E(h2o)", water) == {"oh": 1, "h2": 0.5, "h2o": -1}


def test_a_scaled_equation_balances():
    rows = [row("a", -9.0, ("Si", 3)), row("b", -3.0, ("Si", 1)), row("c", -2.0, ("Si", 1))]
    assert coefficients("(E(a) - E(b) - 2*E(c))/2", rows) == {"a": 0.5, "b": -0.5, "c": -1.0}
    assert check("(E(a) - E(b) - 2*E(c))/2", rows).warnings == ()
    assert check("E(a) - E(b) - 2*E(c) + 0.25", rows).warnings == ()  # a number never counts


@pytest.mark.parametrize("equation", ["E(a)*E(b)", "E(a)/E(b)", "E(a) - 1/(E(b) + 4)"])
def test_an_equation_not_linear_in_the_energies(equation):
    rows = [row("a", -2.0, ("Si", 1)), row("b", -3.0, ("Si", 1))]
    assert coefficients(equation, rows) is None
    assert check(equation, rows).warnings == (NOT_LINEAR,)


def test_an_energy_that_cancels_is_not_used():
    rows = [
        row("a", -2.0, ("Si", 1), ecutwfc=99.0, ecutrho=400.0),
        row("b", -3.0, ("Si", 1), ecutwfc=30.0, ecutrho=240.0),
        row("c", -4.0, ("Si", 1), ecutwfc=30.0, ecutrho=240.0),
    ]
    assert coefficients("E(a) - E(a) + E(b) - E(c)", rows) == {"a": 0, "b": 1, "c": -1}
    assert check("E(a) - E(a) + E(b) - E(c)", rows).warnings == ()  # a's cutoffs do not count
    assert check("E(a) + E(b) - 2*E(c)", rows).warnings[0].startswith("Cutoffs diferentes")


def test_a_row_without_data_stays_out():
    rows = [
        row("a", -2.0, ("Si", 1), ecutwfc=30.0, ecutrho=240.0),
        row("b", -3.0, ("Si", 1)),  # no cutoffs read
        EnergyRow(Path("c.out"), "c", "c", 1, -4.0),  # no level of theory at all
    ]
    assert check("E(a) - E(b) + E(c)", rows).warnings == ()  # not even the balance
    assert check("E(a) - E(b) + E(c)", rows).notes[0] == ZPE


# -- the dipole correction (spec 98 R6) -------------------------------------------------------------
DIPOLE_LINE = "     Computed dipole along edir(3) : \n"  # PW/src/add_efield.f90:178


def with_dipole(lines: list[str]) -> None:
    lines.insert(
        SI_SECOND_SITE + 1, DIPOLE_LINE
    )  # after the second site: ``one_atom`` still finds it


def dipole_set(folder: Path, *names: str) -> list[Path]:
    """``coherent_set`` with the correction in the outputs ``names``."""
    edit = {name: with_dipole for name in names}
    return [
        si_copy(folder, "big", edit=edit.get("big")),
        si_copy(folder, "small", one_atom=True, edit=edit.get("small")),
        si_copy(folder, "atom", one_atom=True, edit=edit.get("atom")),
    ]


EQUATION = "E_ads = E(big) - E(small) - E(atom)"


def test_dipole_correction_on_one_side_warns(tmp_path):
    rows = read_rows(dipole_set(tmp_path / "complex", "big"))
    assert [row.theory.dipole_correction for row in rows if row.theory] == [True, False, False]
    assert check(EQUATION, rows).warnings == (
        "Correção de dipolo em big e não em atom: complexo e substrato precisam da mesma escolha, "
        "ou a diferença de energia leva o termo do dipolo.",
    )
    (warning,) = check(EQUATION, read_rows(dipole_set(tmp_path / "substrate", "atom"))).warnings
    assert warning.startswith("Correção de dipolo em atom e não em big:")


def test_dipole_correction_on_both_or_on_the_adsorbate_only(tmp_path):
    both = read_rows(dipole_set(tmp_path / "both", "big", "atom"))
    assert check(EQUATION, both).warnings == ()
    molecule = read_rows(dipole_set(tmp_path / "molecule", "small"))  # a box of its own
    assert check(EQUATION, molecule).warnings == ()


def test_scanner_reads_the_dipole_correction():
    water = QE_EXAMPLES / "PP" / "dipole_example" / "water.scf.out"  # a real pw.x run with dipfield
    silicon = FIXTURES / "si_bands" / "si.scf.out"
    assert [_facts(path).dipole_correction for path in (water, silicon)] == [True, False]


def _facts(path: Path):
    scanner = Scanner()
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            scanner.feed(number, line)
    return scanner.finish()
