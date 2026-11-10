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


def test_the_last_scf_decides_the_convergence():
    failed = "     convergence NOT achieved after 100 iterations: stopping\n"
    achieved = "     convergence has been achieved in   9 iterations\n"
    later_converged = parse_pw_output(f"number of bfgs steps = 1\n{failed}{achieved}   JOB DONE.\n")
    assert later_converged.converged is True and "SCF não convergiu" not in later_converged.warnings
    assert parse_pw_output(f"{achieved}{failed}   JOB DONE.\n").converged is False
    assert parse_pw_output("head\n", f"{failed}{achieved}").converged is True  # head + tail


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


def test_non_magnetic_spin_orbit_is_noncollinear():
    """noncolin with lspinorb and no magnetization: two-component spinors, as summary.f90 says."""
    out = parse_pw_output("     Non magnetic calculation with spin-orbit\n")
    assert out.noncollinear and not out.spin_polarized


# -- L-02: dynamics that print `new unit-cell volume` without being a variable-cell BFGS ----------
# Texts built from the lines pw.x prints (QE:PW/src/dynamics_module.f90, vcsmd.f90, output_tau.f90).
SCF = "     Self-consistent Calculation\n!    total energy              =     -15.8682760727 Ry\n"
BFGS_VOLUME = "     new unit-cell volume =   2253.94778 a.u.^3 (   334.00060 Ang^3 )\n"
VCSMD_VOLUME = "  new unit-cell volume =    2253.9478 (a.u.)^3\n"
DAMPED_BANNER = "\n     Damped Dynamics Calculation\n"
DAMPED_END = (
    "\n     Damped Dynamics: convergence achieved in   5 steps\n"
    "\n     End of damped dynamics calculation\n"
    "\n     Final energy =     -15.8682760727 Ry\n\n"
    "Begin final coordinates\n" + BFGS_VOLUME + "End final coordinates\n"
)


@pytest.mark.parametrize(
    ("name", "text", "calculation"),
    [
        ("scf", SCF, "scf"),
        ("relax, bfgs", SCF + "     number of bfgs steps    =        1\n", "relax"),
        (
            "vc-relax, bfgs",
            SCF + "     number of bfgs steps    =        1\n" + BFGS_VOLUME,
            "vc-relax",
        ),
        ("relax, damp, running", SCF + DAMPED_BANNER, "relax"),
        ("relax, damp, converged", SCF + DAMPED_BANNER + DAMPED_END, "relax"),
        # Restarted: no banner at step 1, the end marker still says it was a damped dynamics.
        ("relax, damp, restarted and converged", SCF + DAMPED_END, "relax"),
        (
            "relax, fire",
            SCF + "\n     Minimization using the FIRE algorithm\n" + BFGS_VOLUME,
            "relax",
        ),
        (
            "relax, fire, a later step only",
            SCF + "\n     Entering FIRE :   iteration =     7\n",
            "relax",
        ),
        (
            "vc-relax, damp-pr",
            SCF
            + "\n     Parrinello-Rahman Damped Cell Dynamics Minimization: \n"
            + "     convergence thresholds EPSE = 1.00E-04  EPSF = 1.00E-03\n"
            + "\n     Entering Dynamics;  it =     1   time = 0.00000 pico-seconds\n"
            + VCSMD_VOLUME,
            "vc-relax",
        ),
        (
            "vc-relax, cell_dynamics none",
            SCF
            + "\n     Beeman Damped Dynamics Minimization: \n"
            + "\n     Entering Dynamics;  it =     1   time = 0.00000 pico-seconds\n",
            "vc-relax",
        ),
        (
            "vc-md",
            SCF
            + "\n     Entering Dynamics;  it =     3   time = 0.00006 pico-seconds\n"
            + VCSMD_VOLUME,
            "vc-md",
        ),
        (
            "md, verlet",
            SCF
            + "\n     Molecular Dynamics Calculation\n     Entering Dynamics:    iteration =     1\n",
            "md",
        ),
        ("md, langevin", SCF + "\n     Over-damped Langevin Dynamics Calculation\n", "md"),
    ],
)
def test_calculation_of_the_dynamics(name, text, calculation):
    assert parse_pw_output(text).calculation == calculation, name


def test_a_marker_only_in_the_tail_decides_too():
    """Outputs above 16 MB are read as head + tail: the markers may be in either."""
    head = "     Program PWSCF v.7.3.1 starts on  3Jan2025 at  9:46:28\n" + SCF
    tail = "\n     Entering FIRE :   iteration =    40\n" + BFGS_VOLUME
    assert parse_pw_output(head, tail).calculation == "relax"


def test_a_damped_relax_is_not_offered_as_an_scf_nor_as_a_vc_relax(tmp_path):
    from qe_studio.core.calculations.base import output_of
    from qe_studio.core.sniff import FileKind, SniffCache

    header = "     Program PWSCF v.7.3.1 starts on  3Jan2025 at  9:46:28\n"
    runs = {
        "damp": (SCF + DAMPED_BANNER + DAMPED_END, "relax"),
        "md": (SCF + "\n     Molecular Dynamics Calculation\n", "md"),
        "vc-md": (SCF + "\n     Entering Dynamics;  it =     1\n" + VCSMD_VOLUME, "vc-md"),
    }
    for name, (body, calculation) in runs.items():
        path = tmp_path / f"{name}.out"
        path.write_text(header + body)
        sniffed = SniffCache().sniff(path)
        assert (sniffed.kind, sniffed.calculation) == (FileKind.PW_OUT, calculation)
        assert not output_of(FileKind.PW_OUT, "scf")(sniffed)  # no SCF plot, no "from the SCF" menu
        assert output_of(FileKind.PW_OUT, "relax", "vc-relax")(sniffed) is (name == "damp")


# -- L-03: nscf x bands is told by the reference energy line only ----------------------------------
NON_SCF = "     Band Structure Calculation\n     End of band structure calculation\n"


def test_nscf_is_told_from_bands_by_the_reference_energy_line():
    fermi = "\n     the Fermi energy is     8.0584 ev\n"
    homo = "\n     highest occupied level (ev):     6.3143\n"
    homo_lumo = "\n     highest occupied, lowest unoccupied level (ev):     6.3143    6.8182\n"
    assert parse_pw_output(NON_SCF + fermi).calculation == "nscf"
    assert parse_pw_output(NON_SCF + homo).calculation == "nscf"  # fixed occupations
    assert parse_pw_output(NON_SCF + homo_lumo).calculation == "nscf"
    assert parse_pw_output(NON_SCF).calculation == "bands"  # `bands` never prints it


def test_an_nscf_without_the_reference_line_reads_as_bands_known_limit():
    """L-03, accepted: with the default verbosity the text has no other difference. ``lbands`` gates that line
    (``print_ks_energies.f90:24,39``), so an nscf cut before it (still running) and one with
    ``one_atom_occupations`` (which never prints it, ``:192``) look like a bands run."""
    running = parse_pw_output("     Band Structure Calculation\n     Computing kpt #:    12\n")
    assert running.calculation == "bands" and not running.job_done
    one_atom = parse_pw_output(
        NON_SCF + "          k = 0.0000 0.0000 0.0000 ( 100 PWs)   bands (ev):\n"
    )
    assert one_atom.calculation == "bands"
