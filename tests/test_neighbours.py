"""What the detection of a folder reads from other folders (spec 27-8 R4): the one rule that
``infer_from_neighbours``, ``FolderListing.scan`` and ``DetectionService.invalidate`` share."""

import shutil
from pathlib import Path

import pytest

from qe_studio.core.calculations import base
from qe_studio.core.calculations.base import (
    feeds_parent,
    is_neighbour_scf,
    neighbour_scf_folders,
    reads_from,
)
from qe_studio.core.detection import detect_folder
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES

SIBLINGS = ["scf_a", "SCF_b", "02_scf_relaxed", "bands_a", "pdos_a", "relax_a"]


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "proj"
    for name in SIBLINGS:
        (root / name).mkdir(parents=True)
    (root / "scf_notes.txt").write_text("a file, not a folder")
    return root


def bands_without_scf(folder: Path) -> None:
    """A bands run whose own folder has no SCF output."""
    for old, new in [
        ("al.band.in", "bands.in"),
        ("al.band.out", "bands.out"),
        ("bands.out", "bands_pp.out"),
        ("bands.dat.gnu", "bands.dat.gnu"),
    ]:
        shutil.copy(FIXTURES / "al_bands" / old, folder / new)


def test_the_name_predicate_is_case_blind():
    assert is_neighbour_scf("SCF_b") and is_neighbour_scf("02_scf_relaxed")
    assert not is_neighbour_scf("bands_a")


def test_neighbour_folders_are_the_scf_siblings_that_are_folders(project):
    names = [p.name for p in neighbour_scf_folders(project / "bands_a")]
    assert names == ["02_scf_relaxed", "SCF_b", "scf_a"]
    assert [p.name for p in neighbour_scf_folders(project / "scf_a")] == ["02_scf_relaxed", "SCF_b"]
    assert neighbour_scf_folders(project / "missing" / "x") == []


def test_reads_from_agrees_with_the_folders_infer_looks_into(project):
    """Every sibling of every folder: read by it exactly when ``neighbour_scf_folders`` lists it."""
    for key in (project / name for name in SIBLINGS):
        listed = neighbour_scf_folders(key)
        for other in (project / name for name in SIBLINGS if (project / name) != key):
            assert reads_from(key, other) == (other in listed), (key.name, other.name)


def test_reads_from_inside_and_the_scf_siblings(project):
    calc = project / "bands_a"
    assert reads_from(calc, calc) and reads_from(calc / "orbitals", calc)  # itself and below
    assert not reads_from(calc, calc / "orbitals")  # see feeds_parent
    assert reads_from(project / "pdos_a", project / "scf_a")
    assert not reads_from(project / "scf_a", project / "pdos_a")  # the SCF reads nobody


def test_a_subfolder_with_pdos_files_feeds_its_parent(tmp_path):
    """What ``FolderListing.scan`` reads of the immediate subfolders: PDOS files, unless ignored."""
    calc = tmp_path / "calc"
    for name in ("orbitals", "plain", "tmp"):
        (calc / name).mkdir(parents=True)
    (calc / "orbitals" / "pdos.dat.pdos_tot").write_text("# E dos(E) pdos(E)\n")
    (calc / "orbitals" / "pdos.dat.pdos_atm#1(Al)_wfc#1(s)").write_text("")
    (calc / "plain" / "scf.out").write_text("")
    (calc / "tmp" / "pdos.dat.pdos_tot").write_text("")  # an ignored folder is never scanned
    assert feeds_parent(calc / "orbitals")
    assert not feeds_parent(calc / "plain") and not feeds_parent(calc / "tmp")
    assert feeds_parent(calc / "gone")  # its files left the parent too


def test_infer_from_neighbours_goes_through_neighbour_scf_folders(project, monkeypatch):
    shutil.copy(FIXTURES / "al_bands" / "al.scf.out", project / "scf_a" / "scf.out")
    bands = project / "bands_a"
    bands_without_scf(bands)
    cache = SniffCache()

    def inferred() -> list[Path]:
        results = detect_folder(bands, sniff=cache.sniff)
        return next(r for r in results if r.module.kind == "bands").files.get("scf_out", [])

    assert inferred() == [project / "scf_a" / "scf.out"]
    asked = []

    def nobody(folder, pattern=base.NEIGHBOUR_PATTERN):
        asked.append(folder)
        return []

    monkeypatch.setattr(base, "neighbour_scf_folders", nobody)
    assert inferred() == [] and asked == [bands]
