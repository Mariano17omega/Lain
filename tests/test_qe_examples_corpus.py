"""``fixtures/qe_examples/``: what it holds, so a filter never empties the tests in silence."""

import pytest

from conftest import QE_EXAMPLES
from qe_examples_helpers import BANDS, CASES, DATA_FILES, DOS, PP, PROJWFC, PW, select

CALCULATIONS = ("scf", "nscf", "bands", "relax", "vc-relax", "md")
VARIATIONS = (
    "spin",
    "noncollinear",
    "spin_orbit",
    "hubbard",
    "hybrid",
    "vdw",
    "isolated",
    "rism",
    "electric_field",
    "occupations_fixed",
    "occupations_smearing",
    "fixed_magnetization",
    "cell_parameters",
    "k_automatic",
    "k_gamma",
    "k_no_unit",
    "positions_alat",
    "positions_angstrom",
    "positions_crystal",
    "fermi",
    "homo",
    "homo_lumo",
)


@pytest.mark.parametrize("calculation", CALCULATIONS)
def test_every_pw_calculation_has_cases(calculation):
    assert select(PW, [calculation])


@pytest.mark.parametrize("program", [BANDS, PROJWFC, DOS, PP])
def test_every_post_processing_program_has_cases(program):
    assert select(program)


@pytest.mark.parametrize("variation", VARIATIONS)
def test_every_variation_has_a_case(variation):
    assert any(variation in case.covers for case in CASES)


def test_supported_versions_are_present():
    supported = [case for case in CASES if case.supported]
    assert {case.calculation for case in supported} >= {"scf", "relax", "vc-relax", "md"}


def test_support_flag_follows_the_printed_version():
    for case in CASES:
        major_minor = tuple(int(part) for part in case.version.split(".")[:2])
        assert case.supported is (major_minor >= (7, 1)), case.id


def test_every_case_has_its_files():
    for case in CASES:
        assert case.input_path.is_file(), case.input
        assert case.output_path.is_file(), case.output


def test_data_files_exist():
    assert DATA_FILES
    assert all((QE_EXAMPLES / name).is_file() for name in DATA_FILES)


def test_ids_are_unique():
    assert len({case.id for case in CASES}) == len(CASES)


def test_nothing_is_left_outside_the_manifest():
    """Every file there is a case's, a run's data file, or the corpus's own notes."""
    named = {name for case in CASES for name in (case.input, case.output)} | set(DATA_FILES)
    named |= {"manifest.json", "README.md", "LICENSE"}
    found = {p.relative_to(QE_EXAMPLES).as_posix() for p in QE_EXAMPLES.rglob("*") if p.is_file()}
    assert found == named


def test_the_license_of_qe_comes_with_the_corpus():
    assert "GNU GENERAL PUBLIC LICENSE" in (QE_EXAMPLES / "LICENSE").read_text(encoding="utf-8")


def test_inputs_hold_no_shell_left():
    assert [case.input for case in CASES if "$" in case.input_text] == []
