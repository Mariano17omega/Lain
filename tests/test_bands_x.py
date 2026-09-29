import numpy as np
import pytest

from qe_studio.core.qe.bands_x import (
    BandsFormatError,
    parse_bandsx_output,
    path_coordinates,
    read_filband,
    read_gnu,
)

from conftest import FIXTURES

AL_HS_X = [0.0, 0.866, 1.866, 2.2196, 3.2802]


def al_gnu_text():
    return (FIXTURES / "al_bands/bands.dat.gnu").read_text()


def test_read_gnu_al():
    data = read_gnu(al_gnu_text())
    assert (data.n_bands, data.n_kpoints) == (16, 91)
    np.testing.assert_allclose(data.x[[0, 20, 50, 60, 90]], AL_HS_X, atol=1e-4)
    assert data.energies[0, 0] == pytest.approx(3.3227)


def test_read_gnu_single_space_separator():
    # QE 7.1 separates bands with a line holding one space.
    text = "\n".join(" " if not line.strip() else line for line in al_gnu_text().splitlines())
    assert read_gnu(text).energies.shape == (16, 91)


def test_read_gnu_rejects_gnuplot_script():
    with pytest.raises(BandsFormatError):
        read_gnu('set terminal png\nplot "bands.dat.gnu" using 1:2 with lines\n')


def test_read_gnu_rejects_ragged_blocks():
    with pytest.raises(BandsFormatError):
        read_gnu("0.0 1.0\n0.1 1.1\n0.2 1.2\n\n0.0 2.0\n0.1 2.1\n")


def test_read_filband_matches_gnu():
    filband = read_filband((FIXTURES / "al_bands/bands.dat").read_text())
    gnu = read_gnu(al_gnu_text())
    assert filband.energies.shape == (16, 91)
    np.testing.assert_allclose(filband.energies, gnu.energies, atol=2e-3)
    np.testing.assert_allclose(filband.to_band_data().x, gnu.x, atol=2e-4)


def test_filband_touching_fields():
    text = " &plot nbnd=   2, nks=     2 /\n  0.0 0.0 0.0\n-116.798-115.000\n  0.1 0.0 0.0\n -1.0 2.0\n"
    data = read_filband(text)
    np.testing.assert_allclose(data.energies, [[-116.798, -1.0], [-115.0, 2.0]])


def test_path_jump_does_not_advance():
    k = np.array([[0, 0, 0], [0.1, 0, 0], [0.2, 0, 0], [5.0, 5.0, 0], [5.1, 5.0, 0]])
    np.testing.assert_allclose(path_coordinates(k), [0, 0.1, 0.2, 0.2, 0.3])


@pytest.mark.parametrize(
    ("rel", "hs_x", "gnu"),
    [
        ("al_bands/bands.out", AL_HS_X, "bands.dat.gnu"),
        ("si_bands/bands.out", [0.0, 0.866, 1.866, 2.366, 3.0731, 3.6855, 4.7462], "bands.dat.gnu"),
    ],
)
def test_bandsx_output(rel, hs_x, gnu):
    out = parse_bandsx_output((FIXTURES / rel).read_text())
    assert list(out.hs_x) == hs_x
    assert out.gnu_name == gnu
    assert out.filband_name == "bands.dat"
    assert out.job_done


def test_bandsx_joined_negative_coordinates():
    out = parse_bandsx_output((FIXTURES / "si_bands/bands.out").read_text())
    assert out.hs_kpoints[0] == (-0.5, -0.5, 0.5)
