"""Peaks of the bands.x parsers (spec 27-4 R3): measured with ``tracemalloc`` on synthetic files of a
few MB, and compared element by element with the readers they replaced (kept here only)."""

import io
import re
import tracemalloc

import numpy as np
import pytest

from qe_studio.core.qe.bands_x import (
    BandsFormatError,
    FilbandData,
    read_filband,
    read_gnu,
    read_gnu_text,
)
from synthetic import make_filband, make_gnu

from conftest import FIXTURES

_FLOATS = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?")


def old_read_gnu(text: str):
    """``read_gnu(text)`` before spec 27-4: the whole text through ``StringIO`` and ``loadtxt``."""
    data = np.loadtxt(io.StringIO(text), ndmin=2)
    starts = np.flatnonzero(np.diff(data[:, 0]) < 0) + 1
    blocks = np.split(data, starts)
    x = blocks[0][:, 0]
    return x, np.array([block[:, 1] for block in blocks])


def old_read_filband(text: str) -> FilbandData:
    """``read_filband`` before spec 27-4: ``findall`` into a list of ``str``, then of ``float``."""
    nbnd, nks = (int(v) for v in re.search(r"nbnd=\s*(\d+)\s*,\s*nks=\s*(\d+)", text).groups())
    values = np.array([float(v) for v in _FLOATS.findall(text[text.index("/") + 1 :])])
    rows = values[: nks * (3 + nbnd)].reshape(nks, 3 + nbnd)
    return FilbandData(rows[:, :3], rows[:, 3:].T.copy())


def peak_of(fn) -> tuple[int, object]:
    """Bytes allocated at the highest point while ``fn`` ran (above what was held before)."""
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        result = fn()
        return tracemalloc.get_traced_memory()[1] - before, result
    finally:
        tracemalloc.stop()


def test_read_gnu_peak_stays_near_the_size_of_the_file(tmp_path):
    path = tmp_path / "bands.gnu"
    n_bands, n_kpoints = make_gnu(path, mb=4, n_bands=50)
    size = path.stat().st_size
    peak, data = peak_of(lambda: read_gnu(path))
    assert data.energies.shape == (n_bands, n_kpoints)
    assert peak <= 2.5 * size, f"peak {peak / size:.2f}× the file"


def test_read_gnu_result_does_not_keep_the_parsed_table_alive(tmp_path):
    path = tmp_path / "bands.gnu"
    make_gnu(path, mb=4, n_bands=50)
    size = path.stat().st_size
    kept, data = peak_of(lambda: read_gnu(path))
    del kept
    assert data.x.base is None and data.energies.base is None
    assert data.x.nbytes + data.energies.nbytes < 0.5 * size  # not the 16 bytes per line table


def test_read_gnu_matches_the_old_reader_and_the_text_reader(tmp_path):
    path = tmp_path / "bands.gnu"
    make_gnu(path, mb=1, n_bands=20)
    x, energies = old_read_gnu(path.read_text())
    new = read_gnu(path)
    np.testing.assert_array_equal(new.x, x)
    np.testing.assert_array_equal(new.energies, energies)
    as_text = read_gnu_text(path.read_text())
    np.testing.assert_array_equal(new.x, as_text.x)
    np.testing.assert_array_equal(new.energies, as_text.energies)


@pytest.mark.parametrize("name", ["al_bands/bands.dat.gnu", "si_bands/bands.dat.gnu"])
def test_read_gnu_of_the_fixtures_matches_the_old_reader(name):
    path = FIXTURES / name
    x, energies = old_read_gnu(path.read_text())
    new = read_gnu(path)
    np.testing.assert_array_equal(new.x, x)
    np.testing.assert_array_equal(new.energies, energies)


def test_read_gnu_errors_are_format_errors(tmp_path):
    script = tmp_path / "plot.gnu"
    script.write_text('set terminal png\nplot "bands.dat.gnu" using 1:2 with lines\n')
    with pytest.raises(BandsFormatError):
        read_gnu(script)
    binary = tmp_path / "binary.gnu"
    binary.write_bytes(b"\xff\xfe\x00\x01" * 100)
    with pytest.raises(BandsFormatError):
        read_gnu(binary)
    with pytest.raises(OSError):
        read_gnu(tmp_path / "missing.gnu")


def test_read_filband_peak_is_a_few_times_the_text(tmp_path):
    path = tmp_path / "bands.dat"
    n_bands, n_kpoints = make_filband(path, mb=2)
    text = path.read_text()
    peak, data = peak_of(lambda: read_filband(text))
    assert data.energies.shape == (n_bands, n_kpoints)
    assert peak <= 3 * len(text), f"peak {peak / len(text):.2f}× the text"


def test_read_filband_matches_the_old_reader(tmp_path):
    path = tmp_path / "bands.dat"
    make_filband(path, mb=1)
    text = path.read_text()
    old, new = old_read_filband(text), read_filband(text)
    np.testing.assert_array_equal(new.kpoints, old.kpoints)
    np.testing.assert_array_equal(new.energies, old.energies)
    assert new.kpoints.base is None  # a view of the table would keep all of it


def test_read_filband_takes_the_first_numbers_when_there_are_more():
    text = " &plot nbnd=   1, nks=     2 /\n 0.0 0.0 0.0\n 1.5\n 0.1 0.0 0.0\n 2.5\n 9.9 9.9\n"
    np.testing.assert_array_equal(read_filband(text).energies, [[1.5, 2.5]])


def test_read_filband_with_fewer_numbers_than_the_header_is_a_format_error():
    text = " &plot nbnd=   2, nks=     2 /\n 0.0 0.0 0.0\n 1.5 1.6\n 0.1 0.0 0.0\n"
    with pytest.raises(BandsFormatError, match="esperados 2 pontos k com 2 bandas"):
        read_filband(text)


def test_read_filband_with_an_absurd_header_does_not_allocate_for_it():
    text = " &plot nbnd= 99999, nks=999999999 /\n 0.0 0.0 0.0\n 1.5\n"
    with pytest.raises(BandsFormatError):
        read_filband(text)
