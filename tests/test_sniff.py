import os

import numpy as np
import pytest

from qe_studio.core import sniff as sniff_module
from qe_studio.core.sniff import FileKind, SniffCache, looks_like_input
from synthetic import make_gnu, make_long_header_pw

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
        ("qe731_ni_spin_pdos/ni.pdos.out", FileKind.PROJWFC_OUT, None),
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


def test_big_gnu_is_detected_without_loading_it(tmp_path, monkeypatch):
    """Spec 14 R5.1: no size limit, and the sniff streams instead of ``loadtxt``."""
    path = tmp_path / "bands.dat.gnu"
    shape = make_gnu(path, mb=80)
    assert path.stat().st_size > 80 * 2**20

    def no_loadtxt(*args, **kwargs):
        raise AssertionError("the sniff must not loadtxt a .gnu")

    monkeypatch.setattr(np, "loadtxt", no_loadtxt)
    result = SniffCache().sniff(path)
    assert result.kind is FileKind.GNU_DATA
    assert result.shape == shape


def test_big_output_with_a_long_header(tmp_path):
    """Spec 14 R5.2: above 16 MB the facts printed once come from a 256 KB head."""
    path = make_long_header_pw(tmp_path / "scf.out", mb=20, header_kb=100)
    assert path.stat().st_size > 16 * 2**20
    pw = SniffCache().sniff(path).pw
    assert pw is not None
    assert pw.n_kpoints == 47 and pw.n_electrons == 3.0
    assert pw.calculation == "scf" and pw.fermi == 8.0584 and pw.job_done


def test_head_and_tail_are_cut_at_line_ends(tmp_path, monkeypatch):
    """A line split by the head or tail boundary is dropped, never read in part."""
    monkeypatch.setattr(sniff_module, "FULL_READ_LIMIT", 0)
    monkeypatch.setattr(sniff_module, "PW_HEAD_BYTES", 60)
    monkeypatch.setattr(sniff_module, "PW_TAIL_BYTES", 70)
    path = tmp_path / "scf.out"
    path.write_text(
        "     Program PWSCF v.7.3.1 starts on\n"
        "     number of k points=  123\n"  # crosses byte 60: dropped from the head
        + "     filler line\n" * 20
        + "     the Fermi energy is    12.3456 ev\n"  # crosses the tail start: dropped
        + "     Self-consistent Calculation\n   JOB DONE.\n"
    )
    pw = SniffCache().sniff(path).pw
    assert pw is not None
    assert pw.version == "7.3.1" and pw.n_kpoints is None and pw.fermi is None
    assert pw.job_done


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


def test_plot_settings_files_are_never_read(tmp_path, monkeypatch):
    from qe_studio.core import sniff as sniff_module
    from qe_studio.core.calculations.bands import BandsParams
    from qe_studio.core.detection import detect_folder
    from qe_studio.core.plotting.plot_file import write_plot_file

    from conftest import copy_fixture

    folder = copy_fixture("al_bands", tmp_path)
    before = [r.badge for r in detect_folder(folder, sniff=SniffCache().sniff)]
    path = write_plot_file(folder, "bands", BandsParams())

    def no_reading(*_args, **_kwargs):
        raise AssertionError("a .plot file must not be read by the sniffer")

    monkeypatch.setattr(sniff_module, "_read_head", no_reading)
    assert sniff_module.sniff(path).kind is FileKind.UNKNOWN
    monkeypatch.undo()
    assert [r.badge for r in detect_folder(folder, sniff=SniffCache().sniff)] == before


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("al_bands/al.scf.in", True),
        ("al_bands/bands.in", True),
        ("al_pdos_flat/al.projwfc.in", True),
        ("al_bands/al.scf.out", False),
        # bands.x filband: its head is ` &plot nbnd=…, nks=… /`, which is not an input.
        ("al_bands/bands.dat", False),
        ("al_bands/bands.dat.gnu", False),
        ("al_pdos_flat/pdos.dat.pdos_tot", False),
    ],
)
def test_looks_like_input_on_fixtures(rel, expected):
    assert looks_like_input(FIXTURES / rel) is expected


def test_looks_like_input_rescues_what_sniff_gives_up_on(tmp_path):
    # ASE raises on a quote before the `=`: sniff says UNKNOWN, the viewer still shows an input.
    broken = tmp_path / "broken.in"
    broken.write_text("&control\n pre'fix = 'x'\n/\n&system\n/\n")
    assert SniffCache().sniff(broken).kind is FileKind.UNKNOWN
    assert looks_like_input(broken)
    odd_suffix = tmp_path / "si.pw"
    odd_suffix.write_text("&control\n/\n")
    assert looks_like_input(odd_suffix)


def test_looks_like_input_refuses_look_alikes(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("&nbsp; not an input\n")
    binary = tmp_path / "blob"
    binary.write_bytes(b"&control\n\x00\x01")
    notes = tmp_path / "notes.txt"
    notes.write_text("just words\n! total energy\n")
    assert not looks_like_input(page)
    assert not looks_like_input(binary)
    assert not looks_like_input(notes)
    assert not looks_like_input(tmp_path / "missing.in")
