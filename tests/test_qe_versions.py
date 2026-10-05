"""One table of real QE runs, one row per fixture folder, checked per QE version (spec 7, R4).

Lain supports QE >= 7.1 (see ``fixtures/README.md``). Each test below runs over every row that
has the artifact it needs, and checks what differs between versions: the Fermi / HOMO line, the
block separator of ``.gnu`` files (empty line in 7.3, one space in 7.1) and the PDOS column
headers. To add a version, put a real, trimmed run in ``fixtures/qe<version>_<system>/``, add a
``Run`` row and ``git add`` the folder (``test_fixtures_untouched`` fails on untracked files).

7.1 has only pw.x relax outputs so far, and there are no 7.2 or 7.4 runs yet.
"""

from dataclasses import dataclass, field

import numpy as np
import pytest

from qe_studio.core.qe.bands_x import parse_bandsx_output, read_gnu, read_gnu_text
from qe_studio.core.qe.projwfc import header_columns, load_pdos
from qe_studio.core.qe.pw_output import parse_pw_output
from qe_studio.core.sniff import FileKind, SniffCache

from conftest import FIXTURES


@dataclass(frozen=True)
class PwCase:
    calculation: str
    fermi: float | None
    fermi_kind: str | None  # which line gave the reference energy: fermi | homo_lumo | homo
    n_kpoints: int


@dataclass(frozen=True)
class Pdos:
    tot: str
    tot_columns: list[str]
    atm: dict[str, list[str]]  # file name -> header columns
    species: list[str]
    spin: bool = False  # up/down columns


@dataclass(frozen=True)
class Run:
    version: str  # as pw.x prints it ("7.1", "7.3.1")
    folder: str
    pw: dict[str, PwCase] = field(default_factory=dict)  # pw.x outputs
    gnu: dict[str, tuple[int, int]] = field(default_factory=dict)  # file -> (bands, k-points)
    bandsx: dict[str, str] = field(default_factory=dict)  # bands.x output -> its .gnu file
    pdos: Pdos | None = None


RUNS = [
    Run(
        "7.3.1",
        "al_bands",
        pw={
            "al.scf.out": PwCase("scf", 8.0584, "fermi", 47),
            "al.band.out": PwCase("bands", None, None, 91),
        },
        gnu={"bands.dat.gnu": (16, 91)},
        bandsx={"bands.out": "bands.dat.gnu"},
    ),
    Run(
        "7.3.1",
        "si_bands",
        pw={
            "si.scf.out": PwCase("scf", 6.3143, "homo_lumo", 29),
            "si.band.out": PwCase("bands", None, None, 200),
        },
        gnu={"bands.dat.gnu": (16, 200)},
        bandsx={"bands.out": "bands.dat.gnu"},
    ),
    Run(
        "7.3.1",
        "al_pdos_flat",
        pw={
            "al.scf.out": PwCase("scf", 8.0585, "fermi", 47),
            "al.nscf.out": PwCase("nscf", 7.9421, "fermi", 1661),
        },
        pdos=Pdos(
            "pdos.dat.pdos_tot",
            ["dos", "pdos"],
            {
                "pdos.dat.pdos_atm#1(Al)_wfc#1(s)": ["ldos", "pdos"],
                "pdos.dat.pdos_atm#1(Al)_wfc#2(p)": ["ldos", "pdos", "pdos", "pdos"],
            },
            ["Al"],
        ),
    ),
    Run(
        "7.3.1",
        "qe731_ni_spin_bands",
        pw={
            "ni.scf.out": PwCase("scf", 14.2704, "fermi", 29),
            "ni.band.out": PwCase("bands", None, None, 45),
        },
        gnu={"bands_up.dat.gnu": (14, 45), "bands_dw.dat.gnu": (14, 45)},
        bandsx={"bands_up.out": "bands_up.dat.gnu", "bands_dw.out": "bands_dw.dat.gnu"},
    ),
    Run(
        "7.3.1",
        "qe731_ni_spin_pdos",
        pw={
            "ni.scf.out": PwCase("scf", 14.2704, "fermi", 29),
            "ni.nscf.out": PwCase("nscf", 14.2488, "fermi", 72),
        },
        pdos=Pdos(
            "ni.pdos_tot",
            ["dosup", "dosdw", "pdosup", "pdosdw"],
            {
                "ni.pdos_atm#1(Ni)_wfc#1(s)": ["ldosup", "ldosdw", "pdosup", "pdosdw"],
                "ni.pdos_atm#1(Ni)_wfc#2(d)": ["ldosup", "ldosdw"] + ["pdosup", "pdosdw"] * 5,
            },
            ["Ni"],
            spin=True,
        ),
    ),
    Run(
        "7.3.1",
        "qe731_ni_spin_fixed",  # tot_magnetization: two Fermi energies
        pw={"ni.scf.out": PwCase("scf", (13.8484 + 14.1389) / 2, "spin_fermi", 16)},
    ),
    Run("7.3.1", "si_relax", pw={"si.rel.out": PwCase("relax", 6.3142, "homo", 65)}),
    Run("7.1", "kao_vc_relax", pw={"vc-relax.out": PwCase("vc-relax", 2.9523, "homo", 52)}),
    Run(
        "7.1",
        "kao_slab_relax",
        pw={"relax-kaolinite-slab-001.out": PwCase("relax", -3.1462, "homo", 14)},
    ),
    Run(
        "7.1",
        "kao_supercell_relax",
        pw={"relax-kaolinite-slab-001-2x1x.out": PwCase("relax", -3.1463, "homo", 7)},
    ),
]


def cases(attribute: str):
    """``(run, name)`` pairs of every row that has ``attribute``, with readable ids."""
    return [
        pytest.param(run, name, id=f"{run.version}-{run.folder}-{name}")
        for run in RUNS
        for name in getattr(run, attribute)
    ]


def with_separator(text: str, separator: str) -> str:
    """``.gnu`` text with its band separators rewritten (QE 7.3: ""; QE 7.1: " ")."""
    return "\n".join(separator if not line.strip() else line for line in text.splitlines()) + "\n"


def test_table_follows_the_support_policy():
    versions = {tuple(int(part) for part in run.version.split(".")) for run in RUNS}
    assert min(versions) >= (7, 1)
    assert {run.folder for run in RUNS} <= {p.name for p in FIXTURES.iterdir()}


def test_every_fixture_folder_is_documented():
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in FIXTURES.iterdir() if p.is_dir() and f"`{p.name}/`" not in readme]
    assert not missing, f"add these folders to tests/fixtures/README.md: {missing}"


@pytest.mark.parametrize(("run", "name"), cases("pw"))
def test_pw_output(run, name):
    case = run.pw[name]
    path = FIXTURES / run.folder / name
    sniffed = SniffCache().sniff(path)
    assert (sniffed.kind, sniffed.calculation) == (FileKind.PW_OUT, case.calculation)

    out = parse_pw_output(path.read_text())
    assert out.version == run.version
    assert out.calculation == case.calculation
    assert out.fermi == case.fermi
    assert out.fermi_kind == case.fermi_kind
    assert out.n_kpoints == case.n_kpoints
    assert out.job_done


@pytest.mark.parametrize("separator", ["", " "], ids=["blank-line", "single-space"])
@pytest.mark.parametrize(("run", "name"), cases("gnu"))
def test_gnu_separator(run, name, separator):
    text = with_separator((FIXTURES / run.folder / name).read_text(), separator)
    data = read_gnu_text(text)
    assert data.energies.shape == run.gnu[name]
    assert np.all(np.diff(data.x) >= 0) and data.x[0] == 0


@pytest.mark.parametrize(("run", "name"), cases("gnu"))
def test_gnu_is_sniffed(run, name):
    sniffed = SniffCache().sniff(FIXTURES / run.folder / name)
    assert sniffed.kind is FileKind.GNU_DATA
    assert sniffed.shape == run.gnu[name]


@pytest.mark.parametrize(("run", "name"), cases("bandsx"))
def test_bandsx_output(run, name):
    path = FIXTURES / run.folder / name
    assert SniffCache().sniff(path).kind is FileKind.BANDSX_OUT
    out = parse_bandsx_output(path.read_text())
    gnu = run.bandsx[name]
    assert out.gnu_name == gnu and out.job_done
    # The high-symmetry x coordinates span exactly the path the .gnu file plots.
    data = read_gnu(FIXTURES / run.folder / gnu)
    assert out.hs_x[0] == 0
    assert out.hs_x[-1] == pytest.approx(data.x[-1], abs=2e-4)


@pytest.mark.parametrize(
    "run", [pytest.param(r, id=f"{r.version}-{r.folder}") for r in RUNS if r.pdos]
)
def test_pdos_headers_and_loading(run):
    pdos = run.pdos
    folder = FIXTURES / run.folder
    cache = SniffCache()
    assert cache.sniff(folder / pdos.tot).kind is FileKind.PDOS_TOT
    assert header_columns((folder / pdos.tot).open().readline()) == pdos.tot_columns
    for name, columns in pdos.atm.items():
        assert cache.sniff(folder / name).kind is FileKind.PDOS_ATM
        assert header_columns((folder / name).open().readline()) == columns

    data = load_pdos([folder / name for name in pdos.atm], folder / pdos.tot)
    assert data.species == pdos.species
    assert len(data.series) == len(pdos.atm)
    assert data.spin_polarized is pdos.spin and not data.total_is_sum
    assert np.all(np.diff(data.energy) > 0)
