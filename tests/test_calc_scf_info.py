"""Spec 25 R4.1: what "Criar cálculo" reads from the user's SCF."""

import shutil

import pytest

from qe_studio.core.calc_create.kpath import KMesh
from qe_studio.core.calc_create.scf_info import ScfInputError, read_scf, scf_info

from calc_helpers import AL_SCF, NI_SCF, SI_SCF, from_text
from conftest import FIXTURES


def test_facts_of_the_al_scf():
    info = read_scf(AL_SCF)
    assert (info.prefix, info.outdir, info.pseudo_dir) == (
        "al",
        "./tmp",
        "/home/m/Documentos/pseudo",
    )
    assert (info.ibrav, info.nat, info.ntyp, info.nspin) == (2, 1, 1, 1)
    assert (info.ecutwfc, info.ecutrho) == (100.0, 143.0)
    assert (info.occupations, info.smearing, info.degauss) == ("smearing", "gaussian", 0.01)
    assert info.nbnd is None
    assert info.kpoints_option == "automatic"
    assert info.kmesh == KMesh((10, 10, 10), (0, 0, 0))
    assert info.species == ("Al",)
    assert info.crystal is not None and info.structure_problem is None
    assert info.scf_bands == 6  # "number of Kohn-Sham states" of al.scf.out next to it
    assert info.warnings == ()
    assert info.text == AL_SCF.read_text()


def test_spin_and_nbnd():
    ni, si = read_scf(NI_SCF), read_scf(SI_SCF)
    assert ni.nspin == 2 and ni.spin and ni.occupations == "smearing"
    assert si.nbnd == 16 and si.occupations is None and not si.spin
    assert si.crystal is not None and si.crystal.labels == ("Si", "Si")


def test_no_output_next_to_it_means_no_scf_bands(tmp_path):
    shutil.copy(AL_SCF, tmp_path / "scf.in")
    assert read_scf(tmp_path / "scf.in").scf_bands is None


@pytest.mark.parametrize(
    "path, message",
    [
        (FIXTURES / "si_relax" / "si.rel.in", "O arquivo não é um SCF (calculation = 'relax')"),
        (FIXTURES / "al_pdos_flat" / "al.nscf.in", "calculation = 'nscf'"),
        (FIXTURES / "al_pdos_flat" / "al.projwfc.in", "não é um input do pw.x"),
    ],
)
def test_what_is_not_an_scf(path, message):
    with pytest.raises(ScfInputError, match=message.replace("(", r"\(").replace(")", r"\)")):
        read_scf(path)


def test_an_unreadable_file(tmp_path):
    with pytest.raises(ScfInputError, match="Não foi possível ler"):
        read_scf(tmp_path / "missing.in")


def test_no_calculation_is_an_scf():
    text = AL_SCF.read_text().replace("    calculation = 'scf',\n", "")
    assert from_text(text).prefix == "al"


def test_a_structure_the_reader_cannot_build_is_no_error():
    text = AL_SCF.read_text().replace("    celldm(1)=  7.630781648,\n", "")
    info = from_text(text)
    assert info.crystal is None
    assert "celldm(1)" in info.structure_problem


def test_warnings_of_outdir_and_pseudo_dir():
    text = AL_SCF.read_text()
    absolute = text.replace("outdir='./tmp'", "outdir='/scratch/m'")
    assert any("outdir é absoluto (/scratch/m)" in w for w in from_text(absolute).warnings)
    relative = text.replace("'/home/m/Documentos/pseudo'", "'../pseudo'")
    assert any("pseudo_dir relativo (../pseudo)" in w for w in from_text(relative).warnings)
    missing = text.replace("    pseudo_dir = '/home/m/Documentos/pseudo',\n", "")
    assert any("sem pseudo_dir" in w for w in from_text(missing).warnings)


def test_latin_1_input(tmp_path):
    path = tmp_path / "scf.in"
    path.write_bytes(("! c\xe9lula\n" + AL_SCF.read_text()).encode("latin-1"))
    assert read_scf(path).text.startswith("! célula\n")


def test_values_as_written_and_no_prefix():
    text = AL_SCF.read_text().replace("    prefix='al',\n", "")
    info = scf_info(text)
    assert info.prefix == "pwscf"
    assert info.value("system", "ecutwfc") == "100"
    assert info.value("ions", "ion_dynamics") is None
