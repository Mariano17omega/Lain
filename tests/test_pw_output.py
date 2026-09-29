import pytest

from qe_studio.core.qe.pw_output import parse_pw_output, read_structure

from conftest import FIXTURES


@pytest.mark.parametrize(
    ("rel", "calc", "fermi", "kind", "nks", "nelec", "spin", "converged"),
    [
        ("al_bands/al.scf.out", "scf", 8.0584, "fermi", 47, 3.0, False, True),
        ("al_bands/al.band.out", "bands", None, None, 91, 3.0, False, None),
        ("si_bands/si.scf.out", "scf", 6.3143, "homo_lumo", 29, 8.0, False, True),
        ("si_bands/si.band.out", "bands", None, None, 200, 8.0, False, None),
        ("al_pdos_flat/al.nscf.out", "nscf", 7.9421, "fermi", 1661, 3.0, False, None),
        ("ni_pdos_spin/ni.scf.out", "scf", 15.2988, "fermi", 60, 10.0, True, True),
        ("ni_pdos_spin/ni.dos.out", "nscf", 15.3196, "fermi", 72, 10.0, True, None),
        ("si_relax/si.rel.out", "relax", 6.3142, "homo", 65, 8.0, False, True),
    ],
)
def test_fixture_outputs(rel, calc, fermi, kind, nks, nelec, spin, converged):
    out = parse_pw_output((FIXTURES / rel).read_text())
    assert out.calculation == calc
    assert out.fermi == fermi
    assert out.fermi_kind == kind
    assert out.n_kpoints == nks
    assert out.n_electrons == nelec
    assert out.spin_polarized is spin
    assert out.converged is converged
    assert out.job_done
    assert out.version == "7.3.1" or rel.startswith("ni_")


def test_homo_lumo_keeps_lumo():
    out = parse_pw_output((FIXTURES / "si_bands/si.scf.out").read_text())
    assert out.lumo == 6.8182


def test_last_fermi_wins_across_kinds():
    text = (
        "Self-consistent Calculation\n"
        "     the Fermi energy is     1.0000 ev\n"
        "     highest occupied level (ev):     2.5000\n"
        "     End of self-consistent calculation\n"
    )
    out = parse_pw_output(text)
    assert (out.fermi, out.fermi_kind) == (2.5, "homo")
    assert not out.job_done
    assert "execução incompleta (sem JOB DONE)" in out.warnings


def test_spin_fermi_energies_average():
    out = parse_pw_output("the spin up/dw Fermi energies are    5.0000   6.0000 ev\n")
    assert out.fermi == 5.5
    assert out.fermi_up_down == (5.0, 6.0)
    assert any("média" in w for w in out.warnings)


def test_unconverged_and_aborted_runs():
    out = parse_pw_output(
        "     Self-consistent Calculation\n"
        "     convergence NOT achieved after  80 iterations: stopping\n   JOB DONE.\n"
    )
    assert out.calculation == "scf"
    assert out.converged is False
    assert "SCF não convergiu" in out.warnings
    aborted = parse_pw_output("     Band Structure Calculation\n     Davidson diagonalization\n")
    assert aborted.calculation == "bands"


def test_vc_relax_detected():
    text = "number of bfgs steps = 1\nnew unit-cell volume = 1.0\nFinal enthalpy = -1.0 Ry\n"
    assert parse_pw_output(text).calculation == "vc-relax"


def test_structure_despite_ase_units_notice():
    # Raw ASE crashes on this file (``ATOMIC_POSITIONS: units set to alat`` notice).
    atoms = read_structure((FIXTURES / "al_bands/al.scf.out").read_text())
    assert atoms is not None
    assert atoms.get_chemical_formula() == "Al"


def test_structure_none_on_garbage():
    assert read_structure("not a pw.x output") is None
