"""Property tests (Hypothesis) for the parsers that read truncated or hand-edited files.

Profiles ``dev`` and ``ci`` are registered in ``conftest.py`` (``HYPOTHESIS_PROFILE=ci`` in CI).
Specs 9, 11 and 12 add the cases of their new parsers here.

Known limits of ``read_gnu`` the strategies stay clear of (not real ``bands.x`` output): bands
are split where x decreases, so a file with a single k-point (x = 0 for every band) or a band
cut down to one point at x = 0 cannot be split back into bands.
"""

import contextlib

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from qe_studio.core.qe.bands_x import BandsFormatError, read_gnu
from qe_studio.core.qe.relax import parse_relax

# An empty or whitespace-only cut makes numpy warn "input contained no data" before read_gnu
# reports it as a format error.
pytestmark = pytest.mark.filterwarnings("ignore:loadtxt:UserWarning")

# -- bands.x .gnu ------------------------------------------------------------------------------
COLUMN = 12  # each value is written with Fortran's f12.6


@st.composite
def band_matrices(draw, min_bands=1, min_kpoints=2):
    """``(x, energies)``: x strictly increasing from 0, energies of shape (nbnd, nks)."""
    nbnd = draw(st.integers(min_bands, 8))
    nks = draw(st.integers(min_kpoints, 30))
    steps = draw(st.lists(st.floats(1e-3, 2.0), min_size=nks - 1, max_size=nks - 1))
    values = draw(
        st.lists(st.floats(-50, 50, allow_nan=False), min_size=nbnd * nks, max_size=nbnd * nks)
    )
    x = np.concatenate([[0.0], np.cumsum(steps)])
    return x, np.array(values).reshape(nbnd, nks)


def gnu_blocks(x, energies) -> list[list[str]]:
    return [
        [f"{xi:{COLUMN}.6f}{e:{COLUMN}.6f}\n" for xi, e in zip(x, band, strict=True)]
        for band in energies
    ]


def gnu_text(blocks, separator: str, trailing: bool = False) -> str:
    """Bands joined by a blank line (QE 7.3) or a line with one space (QE 7.1)."""
    text = (separator + "\n").join("".join(block) for block in blocks)
    return text + (separator + "\n" if trailing else "")


@given(band_matrices(), st.sampled_from(["", " "]), st.booleans())
def test_read_gnu_round_trip(matrix, separator, trailing):
    x, energies = matrix
    data = read_gnu(gnu_text(gnu_blocks(x, energies), separator, trailing))
    assert data.energies.shape == energies.shape
    np.testing.assert_allclose(data.x, x, atol=1e-6)
    np.testing.assert_allclose(data.energies, energies, atol=1e-6)


@given(band_matrices(), st.sampled_from(["", " "]), st.data())
def test_read_gnu_any_truncation_is_a_format_error_or_a_result(matrix, separator, draw):
    text = gnu_text(gnu_blocks(*matrix), separator)
    cut = draw.draw(st.integers(0, len(text)))
    with contextlib.suppress(BandsFormatError):  # any other exception type fails the test
        read_gnu(text[:cut])


@given(band_matrices(min_bands=2), st.sampled_from(["", " "]), st.integers(0, COLUMN))
def test_read_gnu_cut_inside_the_last_line_is_an_error(matrix, separator, offset):
    """With two or more bands, a last line cut before its energy leaves a short last band."""
    text = gnu_text(gnu_blocks(*matrix), separator)
    last_line = text.rstrip("\n").rfind("\n") + 1
    with pytest.raises(BandsFormatError):
        read_gnu(text[: last_line + offset])


@given(band_matrices(min_bands=2, min_kpoints=3), st.sampled_from(["", " "]), st.data())
def test_read_gnu_bands_of_different_lengths_are_an_error(matrix, separator, draw):
    blocks = gnu_blocks(*matrix)
    band = draw.draw(st.integers(0, len(blocks) - 1))
    row = draw.draw(st.integers(0, len(blocks[band]) - 1))
    del blocks[band][row]
    with pytest.raises(BandsFormatError):
        read_gnu(gnu_text(blocks, separator))


# -- pw.x relax/vc-relax output ----------------------------------------------------------------
RELAX_HEADER = """\
     Program PWSCF v.7.3.1 starts on 30Sep2026 at 12:00:00

     bravais-lattice index     =            0
     number of atoms/cell      =            2
     convergence thresholds EPS_SCF =  1.0E-06 energy convergence thresh.=   1.0000E-04
     force convergence thresh. =   1.0000E-03

   site n.     atom                  positions (alat units)
     1           Si  tau(   1) = (   0.0000000   0.0000000   0.0000000  )
     2           Si  tau(   2) = (   0.2500000   0.2500000   0.2500000  )

"""


def relax_step_lines(energy: float, force: float, k: int, last: str | None) -> str:
    """One BFGS step as pw.x prints it; ``last`` replaces the step line of a converged run."""
    ending = last or f"     number of bfgs steps    =  {k:2d}"
    return (
        "     iteration #  1     ecut=    30.00 Ry     beta= 0.70\n"
        f"!    total energy              =  {energy:16.8f} Ry\n"
        f"     Total force = {force:12.6f}     Total SCF correction = {0.00001:12.6f}\n"
        f"     number of scf cycles    =  {k + 1:2d}\n"
        f"{ending}\n\n"
    )


@st.composite
def relax_runs(draw):
    """``(text, steps)`` of a complete run: ``steps`` is a list of (energy, force)."""
    count = draw(st.integers(1, 8))
    energies = [
        round(v, 8) for v in draw(st.lists(st.floats(-500, -1), min_size=count, max_size=count))
    ]
    forces = [
        round(v, 6) for v in draw(st.lists(st.floats(1e-5, 1.0), min_size=count, max_size=count))
    ]
    converged = draw(st.booleans())
    text = RELAX_HEADER
    for k, (energy, force) in enumerate(zip(energies, forces, strict=True)):
        end = None
        if converged and k == count - 1:
            end = f"     bfgs converged in {count:3d} scf cycles and {k:3d} bfgs steps"
        text += relax_step_lines(energy, force, k, end)
    if converged:
        text += "     End of BFGS Geometry Optimization\n"
    if draw(st.booleans()):
        text += "     JOB DONE.\n"
    return text, list(zip(energies, forces, strict=True))


def parse_text(text: str):
    return parse_relax(text.splitlines(keepends=True))


@given(relax_runs())
def test_parse_relax_reads_every_complete_step(run):
    text, expected = run
    data = parse_text(text)
    assert [(s.energy_ry, s.force_ry_bohr) for s in data.steps] == expected
    assert [s.index for s in data.steps] == list(range(len(expected)))
    assert [s.bfgs_step for s in data.steps] == list(range(len(expected)))  # as printed
    assert data.truncated_steps == 0
    assert data.formula == "Si2"


@given(relax_runs(), st.data())
def test_parse_relax_cut_anywhere_never_raises_and_keeps_a_prefix(run, draw):
    text, expected = run
    cut = draw.draw(st.integers(0, len(text)))
    data = parse_text(text[:cut])
    got = [(s.energy_ry, s.force_ry_bohr) for s in data.steps]
    # The printed step number is not compared: a cut inside "= 12" reads "1".
    assert got == expected[: len(got)]
    assert data.truncated_steps <= 1
    assert [s.index for s in data.steps] == list(range(len(got)))
