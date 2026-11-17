"""Spec 101: relax / vc-relax by damped dynamics (``damp``, ``damp-pr``, ``damp-w``): the parser, the
Resumo and the figure. The real outputs are in ``test_qe_examples_relax.py``; here the text is
synthetic, to pin the corners the examples do not reach."""

import shutil
from pathlib import Path

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from qe_studio.core.calculations import module_for
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.relax import (
    BFGS_DYNAMICS,
    CRITERIA,
    DAMPED_DYNAMICS,
    INPUT,
    parse_relax,
)
from qe_studio.core.sniff import SniffCache, sniff

from conftest import FIXTURES

CONFIG = AppConfig()
RELAX = module_for("relax")
EXAMPLES = FIXTURES / "qe_examples"

HEADER = [
    "     Program PWSCF v.7.3.1 starts on  1Jan2025 at 16: 0: 1",
    "         1           Al  tau(   1) = (   0.0000000   0.0000000   0.0000000  )",
]
FORCES = [
    "     Forces acting on atoms (Cartesian axes, Ry/au):",
    "",
    "     atom    1 type  1   force =     0.00000000    0.00000000    0.01016600",
    "",
]
FINAL_COORDINATES = [
    "Begin final coordinates",
    "     new unit-cell volume =   1193.24211 a.u.^3 (   176.82024 Ang^3 )",
    "",
    "CELL_PARAMETERS (alat=  5.30330000)",
    "   1.000000000   0.000000000   0.000000000",
    "   0.000000000   1.000000000   0.000000000",
    "   0.000000000   0.000000000   8.000000000",
    "",
    "ATOMIC_POSITIONS (alat)",
    "Al       0.500000000   0.500000000  -2.061688086",
    "End final coordinates",
]


def scf(k: int, force: float) -> list[str]:
    return [
        f"!    total energy              =  {-29.2 - 0.05 * (1 - 0.5**k):.8f} Ry",
        *FORCES,
        f"     Total force =     {force:.6f}     Total SCF correction =     0.000045",
    ]


def damped_ions(steps: int, *, converged: bool = True, first: int = 1) -> str:
    """``steps`` SCFs of a relax by ``ion_dynamics = 'damp'``. The last is closed by the
    convergence message, or by an ``Entering Dynamics`` when the run stops at ``nstep``;
    ``first`` is the ``istep`` printed after the first SCF (more than 1 after a restart)."""
    lines = list(HEADER)
    for k in range(steps):
        lines += scf(k, 0.2 * 0.5**k)
        if k == 0 and first == 1:
            lines += ["", "     Damped Dynamics Calculation"]
        if k < steps - 1 or not converged:
            lines += ["", f"     Entering Dynamics:    iteration = {k + first:5d}", ""]
            lines += ["ATOMIC_POSITIONS (alat)", "Al       0.5  0.5  -2.1", ""]
        else:
            lines += [
                "",
                f"     Damped Dynamics: convergence achieved in {k + first - 1:3d} steps",
                "",
                "     End of damped dynamics calculation",
                "",
                "     Final energy =     -29.2237014600 Ry",
                "",
                *FINAL_COORDINATES,
            ]
    lines.append("   JOB DONE.")
    return "\n".join(lines) + "\n"


def damped_cell(steps: int, *, converged: bool = True, thresholds: bool = True) -> str:
    """``steps`` SCFs of a vc-relax by ``cell_dynamics = 'damp-w'``: the volume and cell printed
    after step k are the geometry of step k + 1, as in a BFGS block."""
    lines = list(HEADER)
    for k in range(steps):
        lines += scf(k, 0.2 * 0.5**k)
        lines += [
            "",
            "     Computing stress (Cartesian axis) and pressure",
            "",
            f"          total   stress  (Ry/bohr**3)                   (kbar)     P=  {100 - 20 * k:.2f}",
            "",
        ]
        if k == 0 and thresholds:
            lines += [
                "     Wentzcovitch Damped Cell Dynamics Minimization: ",
                "     convergence thresholds EPSE = 1.00E-05  EPSF = 1.00E-04",
            ]
        if k < steps - 1 or not converged:
            lines += [
                f"     Entering Dynamics;  it = {k + 1:5d}   time =  0.00726 pico-seconds",
                "",
                "  new unit-cell volume =    277.0114 (a.u.)^3",
                f"     new unit-cell volume =    277.0 a.u.^3 (   {40.0 + k:.5f} Ang^3 )",
                "",
                f"CELL_PARAMETERS (alat=  {7.0 + k:.8f})",
                "   1.0   0.0   0.0",
                "   0.0   1.0   0.0",
                "   0.0   0.0   1.0",
                "",
                "ATOMIC_POSITIONS (crystal)",
                "As       0.288384589   0.288384588   0.288384588",
                "",
            ]
        else:
            lines += [
                "     Wentzcovitch Damped Cell Dynamics Minimization: ",
                "     convergence achieved, Efinal=   -25.49946688",
                "",
                "  final unit-cell volume =    274.6211 (a.u.)^3",
                "Begin final coordinates",
                "     new unit-cell volume =    274.62115 a.u.^3 (    40.69466 Ang^3 )",
                "",
                "CELL_PARAMETERS (alat=  7.01033623)",
                "   1.0   0.0   0.0",
                "   0.0   1.0   0.0",
                "   0.0   0.0   1.0",
                "",
                "ATOMIC_POSITIONS (crystal)",
                "As       0.272233124   0.272233115   0.272233115",
                "End final coordinates",
            ]
    lines.append("   JOB DONE.")
    return "\n".join(lines) + "\n"


def parse(text: str, **kwargs):
    return parse_relax(text.splitlines(), **kwargs)


# -- damped ions ---------------------------------------------------------------------------------
def test_damped_ions_steps_count_from_zero_like_bfgs():
    data = parse(damped_ions(5))
    assert data.dynamics == DAMPED_DYNAMICS
    assert [(s.index, s.bfgs_step) for s in data.steps] == [(i, i) for i in range(5)]
    assert data.bfgs_converged and data.converged and data.job_done
    assert data.truncated_steps == 0


def test_damped_ions_fixed_cell_is_a_relax_without_cell_data():
    """The final coordinates carry a ``new unit-cell volume``: no proof of a vc-relax here."""
    data = parse(damped_ions(5))
    assert data.calculation == "relax"
    assert not data.has_volume and not data.has_pressure
    assert all(s.cell is None and s.enthalpy_ry is None for s in data.steps)


def test_damped_ions_converged_at_the_first_scf():
    data = parse(damped_ions(1))
    assert [s.bfgs_step for s in data.steps] == [0] and data.bfgs_converged


def test_damped_ions_that_run_out_of_nstep_are_not_converged():
    data = parse(damped_ions(4, converged=False))
    assert [s.bfgs_step for s in data.steps] == [0, 1, 2, 3]
    assert not data.bfgs_converged and data.truncated_steps == 0


def test_damped_ions_restarted_keep_the_count_of_pw():
    """After a restart ``istep`` comes from the ``.md`` file: the first SCF here is the 7th."""
    data = parse(damped_ions(3, first=7))
    assert [s.bfgs_step for s in data.steps] == [6, 7, 8]
    assert data.bfgs_converged


def test_damped_ions_still_running_leave_the_last_scf_out():
    lines = damped_ions(4, converged=False).splitlines()
    cut = max(i for i, line in enumerate(lines) if line.startswith("!"))
    data = parse("\n".join(lines[: cut + 1]))  # cut at the energy of the 4th SCF: no force yet
    assert [s.bfgs_step for s in data.steps] == [0, 1, 2]
    assert data.truncated_steps == 1 and not data.job_done


def test_damped_ions_thresholds_come_from_the_input():
    """pw.x prints no threshold for them: the input's ``etot_conv_thr`` and ``forc_conv_thr``."""
    data = parse(damped_ions(3), fallback=(2e-5, 5e-4))
    assert (data.energy_threshold, data.force_threshold) == (2e-5, 5e-4)
    assert data.energy_threshold_source == data.force_threshold_source == INPUT


# -- damped cell ---------------------------------------------------------------------------------
def test_damped_cell_is_a_vc_relax_with_pressure_volume_and_cell():
    data = parse(damped_cell(4))
    assert data.dynamics == DAMPED_DYNAMICS and data.calculation == "vc-relax"
    assert [s.bfgs_step for s in data.steps] == [0, 1, 2, 3]
    assert [s.pressure_kbar for s in data.steps] == [100.0, 80.0, 60.0, 40.0]
    assert data.bfgs_converged and data.converged


def test_damped_cell_geometry_belongs_to_the_next_step():
    data = parse(damped_cell(4))
    # step 0's geometry is never printed; step k + 1 gets what block k printed. The final
    # coordinates only fill what is empty (the first-SCF case below), as in a BFGS run.
    assert [s.volume_ang3 for s in data.steps] == [None, 40.0, 41.0, 42.0]
    assert data.steps[0].cell is None and data.steps[1].cell is not None
    assert data.steps[-1].cell is not None
    assert not any(s.enthalpy_ry is not None for s in data.steps)


def test_damped_cell_thresholds_are_the_printed_ones():
    data = parse(damped_cell(3), fallback=(9e-9, 9e-9))
    assert (data.energy_threshold, data.force_threshold) == (1e-5, 1e-4)
    assert data.energy_threshold_source == data.force_threshold_source == CRITERIA


def test_damped_cell_converged_at_the_first_scf():
    data = parse(damped_cell(1))
    assert [s.bfgs_step for s in data.steps] == [0] and data.bfgs_converged
    assert data.calculation == "vc-relax" and data.steps[0].volume_ang3 == 40.69466


def test_damped_cell_that_runs_out_of_nstep_is_not_converged():
    data = parse(damped_cell(3, converged=False))
    assert [s.bfgs_step for s in data.steps] == [0, 1, 2]
    assert not data.bfgs_converged and data.truncated_steps == 0


# -- what BFGS keeps ----------------------------------------------------------------------------
def test_a_bfgs_output_is_not_damped():
    text = "\n".join(
        [
            *HEADER,
            *scf(0, 0.1),
            "     number of scf cycles    =   1",
            "     number of bfgs steps    =   0",
            *scf(1, 0.01),
            "     bfgs converged in   2 scf cycles and   1 bfgs steps",
            "   JOB DONE.",
        ]
    )
    data = parse(text)
    assert data.dynamics == BFGS_DYNAMICS and [s.bfgs_step for s in data.steps] == [0, 1]


# -- the module: Resumo and figure --------------------------------------------------------------
def load(tmp_path: Path, *files: Path):
    folder = tmp_path / "run"
    folder.mkdir()
    for file in files:
        shutil.copy(file, folder / file.name)
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    assert result.kind == "relax"
    dataset = RELAX.load(result, sniff)
    return dataset, RELAX.default_params(CONFIG, dataset)


def render(dataset, params):
    figure = Figure(figsize=params.figure_size, dpi=80)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context(LIGHT.rc(params.font_size)):
        info = RELAX.render(figure, dataset, params, LIGHT)
    figure.canvas.draw()
    return figure, info


def test_damped_ions_example_is_plotted(tmp_path):
    """``example02``: a 7-atom Al slab relaxed by ``ion_dynamics = 'damp'`` (10 SCFs, 9 moves)."""
    example = EXAMPLES / "PW" / "example02"
    dataset, params = load(tmp_path, example / "al001.mm.in", example / "al001.mm.out")
    assert RELAX.summary(dataset).startswith("Relaxado ✓ · 9 passos da dinâmica amortecida")
    figure, info = render(dataset, params)
    energy, force = figure.axes
    assert len(energy.patches) == 9 and force.get_xlabel() == "Passo da dinâmica"
    assert info.notes == ()


def test_damped_cell_example_is_plotted_without_an_enthalpy_note(tmp_path):
    """``VCSexample``: a vc-relax by ``cell_dynamics = 'damp-w'`` (19 SCFs, no enthalpy)."""
    example = EXAMPLES / "PW" / "VCSexample"
    dataset, params = load(tmp_path, example / "As.vcs00.in", example / "As.vcs00.out")
    assert RELAX.summary(dataset).startswith("Relaxado ✓ · 18 passos da dinâmica amortecida")
    params.panels = "all"
    figure, info = render(dataset, params)
    energy, force, pressure, volume = figure.axes
    assert energy.get_ylabel() == "|ΔE| (Ry)" and volume.get_xlabel() == "Passo da dinâmica"
    assert info.notes == ()


def test_one_damped_move_is_singular(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "relax.out").write_text(damped_ions(2))
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    dataset = RELAX.load(result, sniff)
    assert RELAX.summary(dataset).startswith("Relaxado ✓ · 1 passo da dinâmica amortecida")
