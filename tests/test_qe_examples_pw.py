"""Real pw.x runs: what the parsers read from each output, against its input and its own text."""

import pytest

from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.qe.scf import parse_scf
from qe_studio.core.sniff import FileKind, SniffCache

from qe_examples_helpers import (
    PW,
    RISM_CASES,
    RISM_GAP,
    flag_setting,
    last_reference_energy,
    number_setting,
    params,
    reported_iterations,
    select,
    setting,
    total_energies,
    unfinished_hybrid,
)

PW_CASES = select(PW)
SCF_CASES = select(PW, ["scf"])
SCF_GAPS = dict.fromkeys(RISM_CASES, RISM_GAP)


def read(case):
    return parse_pw_output(case.output_text)


@pytest.mark.parametrize("case", params(PW_CASES))
def test_is_sniffed_as_its_calculation(case):
    sniffed = SniffCache().sniff(case.output_path)
    assert (sniffed.kind, sniffed.calculation) == (FileKind.PW_OUT, case.calculation)


@pytest.mark.parametrize("case", params(PW_CASES))
def test_calculation_matches_the_input(case):
    assert read(case).calculation == case.calculation


@pytest.mark.parametrize("case", params(PW_CASES))
def test_version_is_the_printed_one(case):
    version = read(case).version
    assert version is not None and version.startswith(case.version)


@pytest.mark.parametrize("case", params(PW_CASES))
def test_job_done_follows_the_text(case):
    assert read(case).job_done is ("JOB DONE" in case.output_text)


@pytest.mark.parametrize("case", params(PW_CASES))
def test_reference_energy_is_the_last_printed(case):
    expected = last_reference_energy(case.output_text)
    fermi = read(case).fermi
    if expected is None:
        assert fermi is None
    else:
        assert fermi == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    "case", params(select(PW, where=lambda case: setting(case.input_text, "nbnd") is not None))
)
def test_bands_are_the_ones_asked(case):
    assert read(case).n_bands == number_setting(case.input_text, "nbnd")


@pytest.mark.parametrize(
    "case", params(select(PW, where=lambda case: number_setting(case.input_text, "nspin") == 2))
)
def test_spin_polarized_as_asked(case):
    assert read(case).spin_polarized


@pytest.mark.parametrize(
    "case", params(select(PW, where=lambda case: flag_setting(case.input_text, "noncolin")))
)
def test_noncollinear_as_asked(case):
    assert read(case).noncollinear


@pytest.mark.parametrize(
    "case",
    params(
        select(
            PW,
            where=lambda case: (
                setting(case.input_text, "celldm(1)") is not None and case.calculation != "vc-relax"
            ),
        )
    ),
)
def test_alat_is_the_input_celldm(case):
    alat = read(case).alat_bohr
    assert alat == pytest.approx(number_setting(case.input_text, "celldm(1)"), abs=1e-3)


@pytest.mark.parametrize(
    "case",
    params(
        select(PW, ["scf"], where=lambda case: bool(total_energies(case.output_text))), SCF_GAPS
    ),
)
def test_final_energy_is_the_last_printed(case):
    data = parse_scf(case.output_text.splitlines(keepends=True))
    if unfinished_hybrid(case.output_text):
        assert data.final_energy_ry is None  # its "!" energies are of the inner loop
    else:
        assert data.final_energy_ry == pytest.approx(total_energies(case.output_text)[-1], abs=1e-6)


@pytest.mark.parametrize(
    "case",
    params(
        select(PW, ["scf"], where=lambda case: bool(reported_iterations(case.output_text))),
        SCF_GAPS,
    ),
)
def test_iterations_match_the_reported_count(case):
    data = parse_scf(case.output_text.splitlines(keepends=True))
    assert data.status == "converged"
    assert data.n_reported == reported_iterations(case.output_text)[0]
    assert len(data.iterations) == data.n_reported


@pytest.mark.parametrize("case", params(SCF_CASES, SCF_GAPS))
def test_scf_has_iterations(case):
    assert parse_scf(case.output_text.splitlines(keepends=True)).iterations
