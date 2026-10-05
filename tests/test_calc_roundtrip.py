"""Spec 25: a generated folder, once its outputs are there, is what Lain detects and plots.

The outputs are copies of the fixtures' runs, under the names the generated script gives them.
"""

import shutil

from qe_studio.core.calc_create.types import by_id
from qe_studio.core.calc_create.writer import create_folder
from qe_studio.core.calculations.bands import BandsModule
from qe_studio.core.detection import detect_folder
from qe_studio.core.sniff import SniffCache

from calc_helpers import AL_PATH, JOBS, al, ni
from conftest import FIXTURES


def results(folder):
    cache = SniffCache()
    return {r.kind: r for r in detect_folder(folder, sniff=cache.sniff)}, cache


def fill(folder, source, pairs):
    for old, new in pairs:
        shutil.copy(FIXTURES / source / old, folder / new)


def test_bands_folder_is_detected_with_its_path(tmp_path):
    calc = by_id("bandas")
    created = create_folder(tmp_path, calc, "Al", calc.plan(al(), {"kpath": AL_PATH}, JOBS))
    fill(
        created.folder,
        "al_bands",
        [
            ("al.scf.out", "scf.out"),
            ("al.band.out", "bands.out"),
            ("bands.out", "bands_pp.out"),
            ("bands.dat", "bands.dat"),
            ("bands.dat.gnu", "bands.dat.gnu"),
        ],
    )
    found, cache = results(created.folder)
    bands = found["bands"]
    assert bands.plottable
    assert bands.file("bands_in") == created.folder / "bands.in"
    dataset = BandsModule().load(bands, cache.sniff)
    assert dataset.labels == ["L", "Gamma", "X", "U", "Gamma"]


def test_spin_bands_folder_pairs_both_channels(tmp_path):
    calc = by_id("bandas")
    created = create_folder(tmp_path, calc, "Ni", calc.plan(ni(), {"kpath": AL_PATH}, JOBS))
    fill(
        created.folder,
        "qe731_ni_spin_bands",
        [
            ("ni.scf.out", "scf.out"),
            ("ni.band.out", "bands.out"),
            ("bands_up.out", "bands_pp_up.out"),
            ("bands_dw.out", "bands_pp_dw.out"),
            ("bands_up.dat", "bands_up.dat"),
            ("bands_up.dat.gnu", "bands_up.dat.gnu"),
            ("bands_dw.dat", "bands_dw.dat"),
            ("bands_dw.dat.gnu", "bands_dw.dat.gnu"),
        ],
    )
    found, _ = results(created.folder)
    bands = found["bands"]
    assert bands.plottable
    assert [p.name for p in bands.files["gnu"]] == ["bands_up.dat.gnu"]
    assert [p.name for p in bands.files["gnu_down"]] == ["bands_dw.dat.gnu"]


def test_pdos_folder_is_detected(tmp_path):
    calc = by_id("pdos")
    created = create_folder(tmp_path, calc, "Al", calc.plan(al(), {}, JOBS))
    folder = created.folder
    fill(
        folder,
        "al_pdos_flat",
        [
            ("al.scf.out", "scf.out"),
            ("al.nscf.out", "nscf.out"),
            ("al.projwfc.out", "projwfc.out"),
            ("pdos.dat.pdos_tot", "pdos.dat.pdos_tot"),
        ],
    )
    # What the script leaves: projwfc.in/out and pdos_tot in the folder, the projections in orbitals/.
    assert (folder / "projwfc.in").is_file()
    (folder / "orbitals").mkdir()
    for path in (FIXTURES / "al_pdos_flat").glob("*pdos_atm*"):
        shutil.copy(path, folder / "orbitals" / path.name)
    found, _ = results(folder)
    assert found["pdos"].plottable
    assert found["pdos"].file("projwfc_out") == folder / "projwfc.out"
