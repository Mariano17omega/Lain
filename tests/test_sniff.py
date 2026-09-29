import os

import pytest

from qe_studio.core.sniff import FileKind, SniffCache

from conftest import FIXTURES


@pytest.mark.parametrize(
    ("rel", "kind", "calculation"),
    [
        ("al_bands/al.scf.in", FileKind.PW_IN, "scf"),
        ("al_bands/al.scf.out", FileKind.PW_OUT, "scf"),
        ("al_bands/al.band.in", FileKind.PW_IN, "bands"),
        ("al_bands/al.band.out", FileKind.PW_OUT, "bands"),
        ("al_bands/bands.in", FileKind.BANDSX_IN, None),
        ("al_bands/bands.out", FileKind.BANDSX_OUT, None),
        ("al_bands/bands.dat", FileKind.FILBAND, None),
        ("al_bands/bands.dat.gnu", FileKind.GNU_DATA, None),
        ("al_pdos_flat/al.nscf.out", FileKind.PW_OUT, "nscf"),
        ("al_pdos_flat/al.projwfc.in", FileKind.PROJWFC_IN, None),
        ("al_pdos_flat/al.projwfc.out", FileKind.PROJWFC_OUT, None),
        ("al_pdos_flat/pdos.dat.pdos_tot", FileKind.PDOS_TOT, None),
        ("al_pdos_flat/pdos.dat.pdos_atm#1(Al)_wfc#1(s)", FileKind.PDOS_ATM, None),
        ("ni_pdos_spin/ni.pdos.out", FileKind.PROJWFC_OUT, None),
        ("si_relax/si.rel.out", FileKind.PW_OUT, "relax"),
    ],
)
def test_fixture_kinds(rel, kind, calculation):
    result = SniffCache().sniff(FIXTURES / rel)
    assert result.kind is kind
    assert result.calculation == calculation


def test_band_data_shapes():
    cache = SniffCache()
    assert cache.sniff(FIXTURES / "al_bands/bands.dat.gnu").shape == (16, 91)
    assert cache.sniff(FIXTURES / "al_bands/bands.dat").shape == (16, 91)
    bandsx = cache.sniff(FIXTURES / "al_bands/bands.out").bandsx
    assert bandsx.gnu_name == "bands.dat.gnu"


def test_unknown_files(tmp_path):
    cache = SniffCache()
    script = tmp_path / "plot.gnu"
    script.write_text('set term png\nplot "x" u 1:2 w l\n')
    binary = tmp_path / "al.wfc1"
    binary.write_bytes(b"\x00\x01\x02" * 100)
    empty = tmp_path / "job.o12345"
    empty.write_text("")
    image = tmp_path / "bands.png"
    image.write_bytes(b"\x89PNG")
    for path in (script, binary, empty, image):
        assert cache.sniff(path).kind is FileKind.UNKNOWN


def test_kresolved_pdos_warns(tmp_path):
    path = tmp_path / "si.k.pdos_atm#1(Si)_wfc#1(s)"
    path.write_text("# ik    E (eV)  ldos(E)   pdos(E)\n 1 -5.0 0.1 0.1\n")
    result = SniffCache().sniff(path)
    assert result.kind is FileKind.PDOS_ATM
    assert any("resolvida em k" in w for w in result.warnings)


def test_incomplete_run_warns(tmp_path):
    path = tmp_path / "scf.out"
    path.write_text("     Program PWSCF v.7.1 starts on\n     Self-consistent Calculation\n")
    result = SniffCache().sniff(path)
    assert result.calculation == "scf"
    assert result.job_done is False
    assert result.warnings


def test_cache_invalidates_on_change(tmp_path):
    cache = SniffCache()
    path = tmp_path / "x.in"
    path.write_text("&control\n calculation='scf'\n/\n")
    assert cache.sniff(path).calculation == "scf"
    path.write_text("&control\n calculation='bands'\n/\n&system\n/\n")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
    assert cache.sniff(path).calculation == "bands"
