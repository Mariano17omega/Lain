"""The atoms of a pw.x output header, in Å, without ASE (spec 21 R1)."""

import subprocess
import sys

import pytest

from qe_studio.core.qe.structure import BOHR_TO_ANGSTROM, Site, read_sites

from conftest import FIXTURES

ALAT_KAO = 9.7387  # a.u., lattice parameter of kao_vc_relax


def test_single_atom_at_the_origin():
    assert read_sites(FIXTURES / "qe731_ni_spin_pdos/ni.nscf.out") == [Site(1, "Ni", 0.0, 0.0, 0.0)]


def test_positions_are_alat_units_converted_to_angstrom():
    sites = read_sites(FIXTURES / "kao_vc_relax/vc-relax.out")
    assert [s.index for s in sites] == list(range(1, 35))
    assert {s.species for s in sites} >= {"Al", "O"}
    first = sites[0]  # tau(1) = ( 0.1185691 0.8398055 0.6450072 )
    scale = ALAT_KAO * BOHR_TO_ANGSTROM
    assert (first.x, first.y, first.z) == pytest.approx(
        (0.1185691 * scale, 0.8398055 * scale, 0.6450072 * scale)
    )
    assert first.x == pytest.approx(0.61105, abs=1e-4)


def test_species_order_is_the_input_order():
    sites = read_sites(FIXTURES / "si_relax/si.rel.out")
    assert [(s.index, s.species) for s in sites] == [(1, "Si"), (2, "Si")]
    assert sites[1].x == pytest.approx(sites[1].y) == pytest.approx(sites[1].z)


HEADER = "     lattice parameter (alat)  =      10.0000  a.u.\n"
LIST = (
    "     site n.     atom                  positions (alat units)\n"
    "         1           O  tau(   1) = (  -0.5000000   0.0000000   1.0000000  )\n"
    "         2          H1  tau(   2) = (   0.5000000  -0.2500000   0.0000000  )\n"
)


def write(tmp_path, text):
    path = tmp_path / "out"
    path.write_text(text)
    return path


def test_negative_numbers_and_labeled_species(tmp_path):
    sites = read_sites(write(tmp_path, HEADER + LIST + "     number of k points=  3\n"))
    assert [(s.index, s.species) for s in sites] == [(1, "O"), (2, "H1")]
    assert (sites[0].x, sites[0].z) == pytest.approx(
        (-5.0 * BOHR_TO_ANGSTROM, 10.0 * BOHR_TO_ANGSTROM)
    )
    assert sites[1].y == pytest.approx(-2.5 * BOHR_TO_ANGSTROM)


def test_only_the_first_list_is_read(tmp_path):
    again = LIST.replace("O  tau(   1)", "N  tau(   1)")
    sites = read_sites(write(tmp_path, HEADER + LIST + "unrelated line\n" + again))
    assert [s.species for s in sites] == ["O", "H1"]


@pytest.mark.parametrize(
    "text",
    [
        HEADER + "     nothing about sites here\n",  # no list
        LIST,  # a list but no alat to convert with
        "",
        HEADER + "     site n.\n         1   Al  tau(   1) = ( broken )\n",
    ],
)
def test_unusable_headers_give_no_sites(tmp_path, text):
    assert read_sites(write(tmp_path, text)) == []


def test_unreadable_file_gives_no_sites(tmp_path):
    assert read_sites(tmp_path / "missing.out") == []
    assert read_sites(tmp_path) == []  # a directory


def test_reading_sites_does_not_import_ase():
    code = (
        "import sys; from qe_studio.core.qe.structure import read_sites; "
        f"read_sites(r'{FIXTURES / 'kao_vc_relax/vc-relax.out'}'); sys.exit('ase' in sys.modules)"
    )
    assert subprocess.run([sys.executable, "-c", code], timeout=60).returncode == 0
