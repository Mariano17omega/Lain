"""Detection latency (spec 14 R1, report O8): a big project, a huge output, F5 and the startup import.

Run with ``uv run pytest -m perf -s tests/test_perf_detection.py`` to see the timings; the baseline
and the numbers after each optimization are in the notes of ``specs/Archived/spec_14-*.md``, and the budgets
below come from them.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from qe_studio.core.detection import detect_folder
from qe_studio.core.qe.relax import read_relax
from qe_studio.core.sniff import FileKind, SniffCache
from qe_studio.ui.services import DetectionService
from synthetic import make_gnu, make_huge_relax, make_project

# Seconds. Baseline → after spec 14 on the developer's machine (see the spec's notes). Where an
# optimization targeted the measure, the budget is about half the baseline; elsewhere it is
# absolute, with margin for slower machines (the CI perf job never blocks a merge).
BUDGET = {
    "project_cold": 1.5,  # 869 → 548 ms: disk-bound, absolute
    "project_warm": 0.18,  # 361 → 72 ms
    "huge_sniff": 0.1,  # 32 → 8 ms
    "full_sniff": 0.22,  # 446 → 117 ms
    "gnu_sniff": 1.5,  # 541 → 493 ms: the gain is no size limit and bounded memory, absolute
    "refresh": 0.048,  # 96 → 7 ms
    "parse_relax": 2.5,  # 1.29 → 1.12 s (spec 27-7 added the vc-relax fields): absolute
    "import": 0.6,  # 827 → 385 ms: PyQt6 and matplotlib remain; ASE is checked by name below
}
REFRESH_FOLDERS = 50


def report(name: str, seconds: float) -> None:
    print(f"\nperf {name}: {seconds * 1000:.0f} ms")


def timed(action: Callable[[], object]) -> float:
    start = time.perf_counter()
    action()
    return time.perf_counter() - start


@pytest.fixture(scope="session")
def project(tmp_path_factory) -> list[Path]:
    return make_project(tmp_path_factory.mktemp("perf") / "projeto")


@pytest.fixture(scope="session")
def huge_relax(tmp_path_factory) -> Path:
    return make_huge_relax(tmp_path_factory.mktemp("perf_out") / "relax.out")


@pytest.fixture(scope="session")
def full_read_relax(tmp_path_factory) -> Path:
    """Just under ``FULL_READ_LIMIT``: the biggest output the sniff reads whole."""
    return make_huge_relax(tmp_path_factory.mktemp("perf_out") / "relax.out", mb=15)


def _leaves(folders: list[Path]) -> list[Path]:
    return [f for f in folders if f.name.endswith("_calc")]


@pytest.mark.perf
def test_detect_big_project(project):
    cache = SniffCache()

    def detect_all():
        return [detect_folder(folder, sniff=cache.sniff) for folder in project]

    cold = timed(detect_all)
    warm = timed(detect_all)
    report(f"detect {len(project)} folders, cold", cold)
    report(f"detect {len(project)} folders, warm", warm)
    badges = {r.badge for results in detect_all() for r in results}
    assert {"BANDS", "PDOS", "RELAX"} <= badges
    assert cold < BUDGET["project_cold"]
    assert warm < BUDGET["project_warm"]


@pytest.mark.perf
def test_sniff_huge_output(huge_relax):
    cache = SniffCache()
    seconds = timed(lambda: cache.sniff(huge_relax))
    report(f"sniff {huge_relax.stat().st_size // 2**20} MB relax, cold", seconds)
    sniffed = cache.sniff(huge_relax)
    assert sniffed.kind is FileKind.PW_OUT and sniffed.calculation == "relax"
    assert sniffed.job_done
    assert seconds < BUDGET["huge_sniff"]


@pytest.mark.perf
def test_parse_relax_huge_output(huge_relax):
    seconds = min(timed(lambda: read_relax(huge_relax)) for _ in range(2))
    report(f"parse_relax {huge_relax.stat().st_size // 2**20} MB", seconds)
    assert len(read_relax(huge_relax).steps) > 1000
    assert seconds < BUDGET["parse_relax"]


@pytest.mark.perf
def test_sniff_output_read_whole(full_read_relax):
    seconds = min(timed(lambda: SniffCache().sniff(full_read_relax)) for _ in range(3))
    report(f"sniff {full_read_relax.stat().st_size // 2**20} MB relax (read whole), cold", seconds)
    assert SniffCache().sniff(full_read_relax).calculation == "relax"
    assert seconds < BUDGET["full_sniff"]


@pytest.mark.perf
def test_sniff_big_gnu(tmp_path):
    path = tmp_path / "bands.dat.gnu"
    shape = make_gnu(path, mb=60)
    seconds = timed(lambda: SniffCache().sniff(path))
    report(f"sniff {path.stat().st_size // 2**20} MB .gnu, cold", seconds)
    assert SniffCache().sniff(path).shape == shape
    assert seconds < BUDGET["gnu_sniff"]


@pytest.mark.perf
def test_refresh_of_seen_folders(qtbot, project):
    service = DetectionService()
    folders = _leaves(project)[:REFRESH_FOLDERS]
    for folder in folders:
        service.detect_now(folder)

    def refresh():
        service.invalidate()
        for folder in folders:
            service.detect_now(folder)

    seconds = timed(refresh)
    report(f"F5 + detect {len(folders)} folders", seconds)
    assert service.wait()
    assert seconds < BUDGET["refresh"]


def import_main_window() -> tuple[float, set[str]]:
    """Seconds to import ``qe_studio.ui.main_window`` in a fresh interpreter, and the top-level
    packages it loaded (from ``-X importtime``)."""
    run = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", "import qe_studio.ui.main_window"],
        capture_output=True,
        text=True,
        check=True,
    )
    total, packages = 0.0, set()
    for line in run.stderr.splitlines():
        if not line.startswith("import time:") or "|" not in line:
            continue
        fields = [field.strip() for field in line.removeprefix("import time:").split("|")]
        name = fields[2]
        packages.add(name.split(".")[0])
        if name == "qe_studio.ui.main_window":
            total = int(fields[1]) / 1e6
    return total, packages


def test_main_window_import_skips_ase():
    """R2: ASE (and the scipy it pulls) loads on first use, not before the window shows; so do
    pymatgen and jinja2 (spec 25 R1.2)."""
    _seconds, packages = import_main_window()
    assert "qe_studio" in packages
    assert not packages & {"ase", "pymatgen", "spglib", "jinja2"}


def test_calc_create_import_skips_pymatgen_and_jinja2():
    """The window of spec 26 imports the registry and the writer: neither loads them."""
    code = (
        "import sys, qe_studio.core.calc_create.types, qe_studio.core.calc_create.writer, "
        "qe_studio.core.calc_create.kpath, qe_studio.core.calc_create.scf_info, "
        "qe_studio.core.calc_create.preview; "
        "print(sorted(m for m in ('ase', 'pymatgen', 'spglib', 'jinja2') if m in sys.modules))"
    )
    run = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    )
    assert run.stdout.strip() == "[]"


@pytest.mark.perf
def test_import_time():
    seconds = min(import_main_window()[0] for _ in range(3))
    report("import qe_studio.ui.main_window", seconds)
    assert seconds < BUDGET["import"]
