"""Spec 25: a generated folder, once its outputs are there, is what Lain detects and plots.

The outputs are copies of the fixtures' runs, under the names the generated script gives them
(spec 28 R1.5: ``scf_<prefix>.out``, ``nscf_<prefix>.out``, bands.x's ``./band`` files).
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
    assert created.folder.name == "Bands_Al"
    fill(
        created.folder,
        "al_bands",
        [
            ("al.scf.out", "scf_al.out"),
            ("al.band.out", "bands.out"),
            ("bands.out", "bands_pp.out"),
            ("bands.dat", "band"),
            ("bands.dat.gnu", "band.gnu"),
        ],
    )
    found, cache = results(created.folder)
    bands = found["bands"]
    assert bands.plottable
    assert bands.file("bands_in") == created.folder / "bands.in"
    assert bands.file("scf_out") == created.folder / "scf_al.out"
    assert bands.file("gnu") == created.folder / "band.gnu"
    dataset = BandsModule().load(bands, cache.sniff)
    assert dataset.labels == ["L", "Gamma", "X", "U", "Gamma"]


def test_spin_bands_folder_pairs_both_channels(tmp_path):
    calc = by_id("bandas")
    created = create_folder(tmp_path, calc, "Ni", calc.plan(ni(), {"kpath": AL_PATH}, JOBS))
    fill(
        created.folder,
        "qe731_ni_spin_bands",
        [
            ("ni.scf.out", "scf_ni.out"),
            ("ni.band.out", "bands.out"),
            ("bands_up.out", "bands_pp_up.out"),
            ("bands_dw.out", "bands_pp_dw.out"),
            ("bands_up.dat", "band_up"),
            ("bands_up.dat.gnu", "band_up.gnu"),
            ("bands_dw.dat", "band_dw"),
            ("bands_dw.dat.gnu", "band_dw.gnu"),
        ],
    )
    found, _ = results(created.folder)
    bands = found["bands"]
    assert bands.plottable
    # Paired by the bands.x inputs (spin_component, filband = './band_up' / './band_dw').
    assert [p.name for p in bands.files["gnu"]] == ["band_up.gnu"]
    assert [p.name for p in bands.files["gnu_down"]] == ["band_dw.gnu"]
    assert not any("canal" in warning for warning in bands.warnings), bands.warnings


def test_pdos_folder_is_detected(tmp_path):
    calc = by_id("pdos")
    created = create_folder(tmp_path, calc, "", calc.plan(al(), {}, JOBS))
    folder = created.folder
    assert folder.name == "PDOS"
    fill(
        folder,
        "al_pdos_flat",
        [
            ("al.scf.out", "scf_al.out"),
            ("al.nscf.out", "nscf_al.out"),
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
    pdos = found["pdos"]
    assert pdos.plottable
    assert pdos.file("projwfc_out") == folder / "projwfc.out"
    assert pdos.file("scf_out") == folder / "scf_al.out"
    assert pdos.file("nscf_out") == folder / "nscf_al.out"


def test_charge_folder_gets_the_scf_badge(tmp_path):
    """Spec 29 R5.3: nothing detects pp.x; the SCF output next to its inputs is what shows."""
    calc = by_id("charge")
    created = create_folder(tmp_path, calc, "Al", calc.plan(al(), {}, JOBS, name="Al"))
    folder = created.folder
    assert folder.name == "Charge_Al"
    assert [p.name for p in created.files] == ["charge.qsub", "scf_al.in", "pp_Al_charge.in"]
    fill(folder, "al_bands", [("al.scf.out", "scf_al.out")])
    found, _ = results(folder)
    assert set(found) == {"scf"}  # no module takes the pp.x input
    assert found["scf"].badge == "SCF"
    assert found["scf"].file("scf_out") == folder / "scf_al.out"
