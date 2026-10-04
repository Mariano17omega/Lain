import pytest

from qe_studio.core.qe.pw_output import parse_pw_output, read_structure
from qe_studio.core.qe.structure import header_formula

from conftest import FIXTURES


@pytest.mark.parametrize(
    ("rel", "calc", "fermi", "kind", "nks", "nelec", "spin", "converged"),
    [
        ("al_bands/al.scf.out", "scf", 8.0584, "fermi", 47, 3.0, False, True),
        ("al_bands/al.band.out", "bands", None, None, 91, 3.0, False, None),
        ("si_bands/si.scf.out", "scf", 6.3143, "homo_lumo", 29, 8.0, False, True),
        ("si_bands/si.band.out", "bands", None, None, 200, 8.0, False, None),
        ("al_pdos_flat/al.nscf.out", "nscf", 7.9421, "fermi", 1661, 3.0, False, None),
        ("qe731_ni_spin_bands/ni.scf.out", "scf", 14.2704, "fermi", 29, 10.0, True, True),
        ("qe731_ni_spin_pdos/ni.nscf.out", "nscf", 14.2488, "fermi", 72, 10.0, True, None),
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
    assert out.version == "7.3.1"


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


def test_magnetization_is_the_last_scf_iteration():
    out = parse_pw_output(
        "     total magnetization       =     0.50 Bohr mag/cell\n"
        "     absolute magnetization    =     0.60 Bohr mag/cell\n"
        "     total magnetization       =     0.62 Bohr mag/cell\n"
        "     absolute magnetization    =     0.70 Bohr mag/cell\n"
    )
    assert out.total_magnetization == 0.62
    assert out.absolute_magnetization == 0.70


def test_noncollinear_total_magnetization_is_the_norm_of_the_vector():
    out = parse_pw_output(
        "     total magnetization       =     0.00     3.00    -4.00 Bohr mag/cell\n"
    )
    assert out.total_magnetization == pytest.approx(5.0)


def test_magnetization_of_runs_without_spin_is_none():
    out = parse_pw_output((FIXTURES / "al_bands/al.scf.out").read_text())
    assert out.total_magnetization is None and out.absolute_magnetization is None


@pytest.mark.parametrize(
    ("rel", "total", "absolute"),
    [
        ("qe731_ni_spin_bands/ni.scf.out", 0.71, 0.81),
        ("qe731_ni_spin_fixed/ni.scf.out", 0.50, 0.63),
    ],
)
def test_magnetization_of_the_spin_fixtures(rel, total, absolute):
    out = parse_pw_output((FIXTURES / rel).read_text())
    assert out.spin_polarized
    assert (out.total_magnetization, out.absolute_magnetization) == (total, absolute)


def test_two_fermi_energies_warning_says_what_the_plots_do():
    out = parse_pw_output((FIXTURES / "qe731_ni_spin_fixed/ni.scf.out").read_text())
    assert out.fermi_kind == "spin_fermi" and out.fermi_up_down == (13.8484, 14.1389)
    assert out.fermi == pytest.approx(13.99365)
    assert "duas energias de Fermi (↑/↓): referência na média, linhas separadas no gráfico" in (
        out.warnings
    )


@pytest.mark.parametrize(
    ("rel", "up_down"),
    [
        ("qe731_ni_spin_fixed/ni.scf.out", (5.25, 4.75)),  # tot_magnetization: printed per channel
        ("qe731_ni_spin_bands/ni.scf.out", None),
        ("al_bands/al.scf.out", None),
    ],
)
def test_electrons_per_spin_channel(rel, up_down):
    out = parse_pw_output((FIXTURES / rel).read_text())
    assert out.n_electrons_up_down == up_down


@pytest.mark.parametrize(
    ("rel", "formula"),
    [
        ("al_bands/al.scf.out", "Al"),
        ("si_bands/si.scf.out", "Si2"),
        ("kao_slab_relax/relax-kaolinite-slab-001.out", "Al4Si4O18H8"),
        ("kao_vc_relax/vc-relax.out", "Al4Si4O18H8"),  # ASE's read_structure gives up on it
    ],
)
def test_header_formula(rel, formula):
    """Spec 14 R6.3: the formula of the bands dataset comes from the header, without ASE."""
    assert header_formula(FIXTURES / rel) == formula


def test_header_formula_reads_only_the_first_site_list(tmp_path):
    path = tmp_path / "scf.out"
    path.write_text(
        "     site n.     atom                  positions (alat units)\n"
        "         1           Ga  tau(   1) = (   0.0000000   0.0000000   0.0000000  )\n"
        "         2           As  tau(   2) = (   0.2500000   0.2500000   0.2500000  )\n"
        "\n"
        "     Crystallographic axes\n"
        "         1           Ga  tau(   1) = (  0.0000000  0.0000000  0.0000000  )\n"
    )
    assert header_formula(path) == "GaAs"
    path.write_text("     number of k points=    10\n         1  Si  tau(   1) = ( 0 0 0 )\n")
    assert header_formula(path) is None
    assert header_formula(tmp_path / "missing.out") is None
