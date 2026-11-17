"""Real bands.x, projwfc.x, dos.x and pp.x runs, and the data files they wrote."""

import re

import numpy as np
import pytest

from qe_studio.core.qe.bands_x import (
    parse_bandsx_output,
    read_filband,
    read_filband_header,
    read_gnu,
)
from qe_studio.core.qe.lowdin import read_lines, read_lowdin
from qe_studio.core.qe.projwfc import header_columns, load_pdos
from qe_studio.core.sniff import FileKind, SniffCache

from conftest import QE_EXAMPLES
from qe_examples_helpers import BANDS, DOS, PP, PROJWFC, params, select

_HIGH_SYMMETRY = re.compile(r"high-symmetry point:")
_SPILLING = re.compile(r"Spilling Parameter:\s*(-?\d+\.\d+)")
KINDS = {
    BANDS: FileKind.BANDSX_OUT,
    PROJWFC: FileKind.PROJWFC_OUT,
    DOS: FileKind.DOS_OUT,
    PP: FileKind.PP_OUT,
}
FILBANDS = {
    "PP/example01/sibands.dat": None,
    "PP/exx_scf_bands_example/sibands.dat": "PP/exx_scf_bands_example/sibands.dat.gnu",
}
PDOS = {
    "PP/example02": ("ni", {"Ni"}, True),
    "PP/fermisurf_example": ("mgb2", {"Mg", "B"}, False),
}


@pytest.mark.parametrize("case", params(select(BANDS) + select(PROJWFC) + select(DOS) + select(PP)))
def test_output_is_sniffed_by_its_banner(case):
    assert SniffCache().sniff(case.output_path).kind is KINDS[case.program]


@pytest.mark.parametrize("case", params(select(BANDS)))
def test_bands_x_reads_the_high_symmetry_points(case):
    out = parse_bandsx_output(case.output_text)
    assert out.job_done is ("JOB DONE" in case.output_text)
    assert len(out.hs_x) == len(_HIGH_SYMMETRY.findall(case.output_text))


@pytest.mark.parametrize("name", sorted(FILBANDS))
def test_filband_has_the_announced_shape(name):
    text = (QE_EXAMPLES / name).read_text()
    header = read_filband_header(text)
    assert header is not None
    nbnd, nks = header
    data = read_filband(text)
    assert data.energies.shape == (nbnd, nks)
    assert data.kpoints.shape == (nks, 3)
    assert SniffCache().sniff(QE_EXAMPLES / name).kind is FileKind.FILBAND


def test_gnu_agrees_with_the_filband_of_the_same_run():
    folder = QE_EXAMPLES / "PP/exx_scf_bands_example"
    gnu = read_gnu(folder / "sibands.dat.gnu")
    filband = read_filband((folder / "sibands.dat").read_text())
    assert gnu.energies.shape == filband.energies.shape
    assert np.allclose(gnu.energies, filband.energies, atol=2e-3)
    assert SniffCache().sniff(folder / "sibands.dat.gnu").kind is FileKind.GNU_DATA


def pdos_files(folder: str, prefix: str):
    root = QE_EXAMPLES / folder
    return sorted(root.glob(f"{prefix}.pdos_atm*")), root / f"{prefix}.pdos_tot"


@pytest.mark.parametrize("folder", sorted(PDOS))
def test_pdos_files_are_sniffed(folder):
    atm, total = pdos_files(folder, PDOS[folder][0])
    assert atm
    cache = SniffCache()
    assert {cache.sniff(path).kind for path in atm} == {FileKind.PDOS_ATM}
    assert cache.sniff(total).kind is FileKind.PDOS_TOT


@pytest.mark.parametrize("folder", sorted(PDOS))
def test_pdos_species_and_spin(folder):
    prefix, species, spin = PDOS[folder]
    atm, total = pdos_files(folder, prefix)
    data = load_pdos(atm, total)
    assert set(data.species) == species
    assert data.spin_polarized is spin
    assert data.total is not None and not data.total_is_sum


@pytest.mark.parametrize("folder", sorted(PDOS))
def test_pdos_header_names_the_columns(folder):
    prefix, _species, spin = PDOS[folder]
    _atm, total = pdos_files(folder, prefix)
    columns = header_columns(total.read_text().splitlines()[0])
    assert columns == (["dosup", "dosdw", "pdosup", "pdosdw"] if spin else ["dos", "pdos"])


@pytest.mark.parametrize("folder", sorted(PDOS))
def test_projected_series_add_up_to_the_total_projection(folder):
    """projwfc.x writes in ``pdos_tot`` the sum of what it projected on each orbital."""
    prefix, _species, spin = PDOS[folder]
    atm, total = pdos_files(folder, prefix)
    data = load_pdos(atm, total)
    table = np.loadtxt(total, skiprows=1)
    # Each value is written with three or four significant digits, hence the relative tolerance.
    summed = sum(series.channel.up for series in data.series)
    assert np.allclose(summed, table[:, 3 if spin else 2], rtol=1e-2, atol=5e-3)
    if spin:
        down = sum(series.channel.down for series in data.series)
        assert np.allclose(down, table[:, 4], rtol=1e-2, atol=5e-3)


LOWDIN = [case for case in select(PROJWFC) if "Spilling Parameter" in case.output_text]


def test_the_corpus_has_lowdin_blocks():
    assert len(LOWDIN) >= 4  # Ni and Pt (spin-orbit) PDOS, MgB2, H2 (spec 99)


@pytest.mark.parametrize("case", params(LOWDIN))
def test_projwfc_lowdin_block(case):
    """The block of ``print_lowdin`` (spec 99): the spilling QE printed, and the charges add up as QE
    summed them (to the four decimals of ``f8.4``)."""
    found = read_lines(case.output_text.splitlines())
    assert found is not None and found.atoms
    assert found.spilling == float(_SPILLING.findall(case.output_text)[-1])
    for atom in found.atoms:
        assert sum(atom.orbitals.values()) == pytest.approx(atom.total, abs=1e-3)
        if atom.up is not None and atom.down is not None and atom.polarization is not None:
            assert atom.up + atom.down == pytest.approx(atom.total, abs=1e-3)
            assert atom.up - atom.down == pytest.approx(atom.polarization, abs=1e-3)
    tail = read_lowdin(case.output_path)  # the end of the file has the whole block
    assert tail is not None and (tail.atoms, tail.spilling) == (found.atoms, found.spilling)
