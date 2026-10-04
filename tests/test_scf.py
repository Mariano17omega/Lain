"""Spec 9: SCF convergence parser, module and figure."""

import time
import warnings
from dataclasses import asdict
from pathlib import Path

import matplotlib
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from qe_studio.core.calculations import module_for, module_for_file
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.calculations.params import ordered_sections
from qe_studio.core.calculations.scf import NO_DELTAS, NO_PANELS, ScfParams
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder, manual_result
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.scf import parse_scf, read_scf
from qe_studio.core.sniff import SniffCache, sniff

from conftest import FIXTURES, copy_fixture

CONFIG = AppConfig()
SCF = module_for("scf")
AL = FIXTURES / "al_bands" / "al.scf.out"
NI = FIXTURES / "qe731_ni_spin_bands" / "ni.scf.out"  # nspin = 2


def synthetic(
    count: int,
    end: str = "converged",
    spin: bool = False,
    threshold: bool = True,
    filler: int = 0,
    cycles: int = 1,
    flat: bool = False,
) -> str:
    """A pw.x SCF output with ``count`` iterations; ``end``: converged | not | running."""
    lines = ["     Program PWSCF v.7.3.1 starts on  1Jan2025 at 16: 0: 1", ""]
    if threshold:
        lines.append("     scf convergence threshold =      1.0E-08")
    lines += [
        "     mixing beta               =       0.7000",
        "     number of iterations used =            8  plain     mixing",
        "",
        "     Self-consistent Calculation",
        "",
    ]
    for _ in range(cycles):
        for k in range(1, count + 1):
            last = k == count and end == "converged"
            energy = -10.0 if flat else -10.0 - 0.1 * 0.5**k
            lines.append(f"     iteration #{k:3d}     ecut=    30.00 Ry     beta= 0.70")
            lines += ["     Davidson diagonalization with overlap"] * filler
            lines += [
                f"     total cpu time spent up to now is {k:10.1f} secs",
                "",
                f"{'!' if last else ' '}    total energy              =  {energy:14.8f} Ry",
                f"     estimated scf accuracy    <  {0.1 * 0.1**k:.2E} Ry",
            ]
            if spin:
                lines += [
                    "     total magnetization       =     1.85 Bohr mag/cell",
                    "     absolute magnetization    =     1.87 Bohr mag/cell",
                ]
            lines.append("")
        if end == "converged":
            lines.append(f"     convergence has been achieved in {count:3d} iterations")
        elif end == "not":
            lines.append(f"     convergence NOT achieved after {count:3d} iterations: stopping")
    if end != "running":
        lines.append("   JOB DONE.")
    return "\n".join(lines) + "\n"


def load(path: Path):
    """The plot of one output file, as the context menu's "Plotar" builds it."""
    result = manual_result(SCF, path.parent, {"scf_out": [path]}, SniffCache().sniff)
    dataset = SCF.load(result, sniff)
    return result, dataset, SCF.default_params(CONFIG, dataset)


def write(tmp_path: Path, text: str, name: str = "scf.out") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def render(dataset, params):
    figure = Figure(figsize=params.figure_size, dpi=80)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context(LIGHT.rc(params.font_size)):
        info = SCF.render(figure, dataset, params, LIGHT)
    figure.canvas.draw()
    return figure, info


# -- parser ------------------------------------------------------------------------------------
def test_al_scf():
    data = read_scf(AL)
    assert [it.index for it in data.iterations] == [1, 2, 3, 4]
    first, last = data.iterations[0], data.iterations[-1]
    assert (first.energy_ry, first.accuracy_ry) == (-5.03857033, 0.00554324)
    assert (first.ecut_ry, first.beta, first.cpu_s) == (100.0, 0.7, 1.0)
    assert last.energy_ry == -5.03855495  # from the "!" line
    assert last.accuracy_ry == 3.7e-09  # "3.7E-09"
    assert data.final_energy_ry == -5.03855495
    assert (data.threshold_ry, data.mixing_beta, data.mixing_mode) == (1e-8, 0.7, "plain")
    assert (data.status, data.n_reported) == ("converged", 4)
    assert data.job_done and not data.spin and data.truncated == 0 and data.cycles == 1


def test_si_scf():
    data = read_scf(FIXTURES / "si_bands" / "si.scf.out")
    assert len(data.iterations) == 7 and data.status == "converged" and data.n_reported == 7
    assert data.iterations[-1].energy_ry == data.final_energy_ry == -15.86827608


def test_spin_scf_has_the_magnetization_of_every_iteration():
    data = read_scf(NI)
    assert len(data.iterations) == 12 and data.status == "converged" and data.spin
    first = data.iterations[0]
    assert (first.total_mag, first.abs_mag) == (2.15, 2.16)
    assert all(it.total_mag is not None and it.abs_mag is not None for it in data.iterations)
    assert (data.iterations[-1].total_mag, data.iterations[-1].abs_mag) == (0.71, 0.81)


def test_harris_foulkes_estimate_is_read_when_printed():
    text = synthetic(2).replace(
        "     estimated scf accuracy",
        "     Harris-Foulkes estimate   =     -10.05000000 Ry\n     estimated scf accuracy",
    )
    assert parse_scf(text.splitlines()).iterations[0].harris_ry == -10.05


def test_noncollinear_magnetization_is_the_norm_of_the_vector():
    text = synthetic(2).replace(
        "     total energy ",
        "     total magnetization       =     0.00    3.00    4.00 Bohr mag/cell\n     total energy ",
    )
    assert parse_scf(text.splitlines()).iterations[0].total_mag == 5.0


def test_truncated_output(tmp_path):
    folder = copy_fixture("al_bands", tmp_path)
    out = folder / "al.scf.out"
    lines = out.read_text().splitlines(keepends=True)
    fourth = next(i for i, line in enumerate(lines) if "iteration #  4" in line)
    out.write_text("".join(lines[: fourth + 3]))  # inside iteration 4: no energy, no accuracy yet
    _result, dataset, _params = load(out)
    data = dataset.data
    assert len(data.iterations) == 3 and data.truncated == 1
    assert data.status == "running" and not data.job_done and data.final_energy_ry is None
    assert "1 iteração incompleta ignorada" in dataset.warnings
    assert any("sem JOB DONE" in w for w in dataset.warnings)
    assert SCF.summary(dataset).startswith("Em andamento · 3 iterações · precisão 5.8e-07 Ry")


def test_not_converged(tmp_path):
    _result, dataset, params = load(write(tmp_path, synthetic(3, end="not")))
    data = dataset.data
    assert (data.status, data.n_reported, data.final_energy_ry) == ("not_converged", 3, None)
    assert SCF.summary(dataset) == (
        "Não convergiu ✗ após 3 iterações · precisão 1.0e-04 Ry (limiar 1.0e-08)"
    )
    figure, _info = render(dataset, params)
    assert [t.get_text() for t in figure.axes[0].texts] == ["convergência NÃO atingida"]


def test_running_run_has_its_own_note(tmp_path):
    _result, dataset, params = load(write(tmp_path, synthetic(3, end="running")))
    assert dataset.data.status == "running"
    figure, _info = render(dataset, params)
    assert [t.get_text() for t in figure.axes[0].texts] == ["em andamento"]


def test_only_the_first_cycle_is_read(tmp_path):
    _result, dataset, _params = load(write(tmp_path, synthetic(3, cycles=3)))
    assert len(dataset.data.iterations) == 3 and dataset.data.cycles == 3
    assert "saída com 3 ciclos SCF; mostrando o primeiro" in dataset.warnings
    assert dataset.data.status == "converged" and dataset.data.job_done


def test_missing_threshold(tmp_path):
    _result, dataset, params = load(write(tmp_path, synthetic(3, threshold=False)))
    assert dataset.data.threshold_ry is None
    assert "limiar de convergência não encontrado no cabeçalho" in dataset.warnings
    assert "limiar" not in SCF.summary(dataset)
    figure, _info = render(dataset, params)
    assert len(figure.axes[0].get_lines()) == 1  # no conv_thr line


def test_no_complete_iteration_is_a_load_error(tmp_path):
    path = write(tmp_path, synthetic(1, end="running").split("     total energy")[0], "run.out")
    result = manual_result(SCF, tmp_path, {"scf_out": [path]}, SniffCache().sniff)
    with pytest.raises(LoadError, match="Nenhuma iteração SCF completa em run.out"):
        SCF.load(result, sniff)


# -- detection and the single-file hooks --------------------------------------------------------
def test_scf_only_folder_is_plottable_and_keyed_by_its_output(tmp_path):
    out = write(tmp_path, AL.read_text(), "al.scf.out")
    (result,) = detect_folder(tmp_path, sniff=SniffCache().sniff)
    assert result.kind == "scf" and result.plottable and result.plot_target == out
    assert SCF.display_name == "Convergência SCF" and result.badge == "SCF"


def test_plot_target_is_the_folder_for_the_other_modules(tmp_path):
    assert module_for("bands").plot_target(tmp_path, {}) == tmp_path
    assert module_for("relax").single_file_role is None
    assert SCF.plot_target(tmp_path, {}) == tmp_path  # nothing mapped yet


@pytest.mark.parametrize(
    "path, plottable",
    [
        (AL, True),
        (FIXTURES / "si_bands" / "si.scf.out", True),
        (FIXTURES / "al_bands" / "al.band.out", False),  # pw.x bands
        (FIXTURES / "al_bands" / "bands.out", False),  # bands.x
        (FIXTURES / "si_relax" / "si.rel.out", False),
        (FIXTURES / "al_bands" / "al.scf.in", False),
    ],
)
def test_only_scf_outputs_are_plottable_alone(path, plottable):
    module = module_for_file(SniffCache().sniff(path))
    assert (module is SCF) == plottable and (module is None) == (not plottable)
    assert module_for_file(None) is None


# -- parameters ----------------------------------------------------------------------------------
def test_schema_defaults_and_export_stem(tmp_path):
    _r, plain, params = load(write(tmp_path, synthetic(3)))
    names = {f.name for f in SCF.param_schema(plain)}
    assert "show_magnetization" not in names and "magnetization_color" not in names
    assert params.figure_height == pytest.approx(CONFIG.plot.figure_size[1] * 1.5)
    assert params.show_legend and (params.energy_mode, params.scale) == ("delta", "log")
    _r, spin, params = load(write(tmp_path, synthetic(3, spin=True), "spin.out"))
    assert {"show_magnetization", "magnetization_color"} <= {f.name for f in SCF.param_schema(spin)}
    assert params.figure_height == pytest.approx(CONFIG.plot.figure_size[1] * 2.0)
    sections = [s.name for s in ordered_sections(SCF)]
    assert sections.index("Convergência") < sections.index("Eixo X") < sections.index("Estilo")
    assert {f.section for f in SCF.param_schema(spin)} <= set(sections)
    assert SCF.export_stem(params) == "scf" and SCF.view_fields == ("xmin", "xmax")


def test_plot_file_round_trip_validates_the_hidden_color(tmp_path):
    _r, plain, _p = load(write(tmp_path, synthetic(3)))
    params = ScfParams(scale="linear", energy_mode="total", xmin=2.0, accuracy_color="#123456")
    write_plot_file(tmp_path, "scf", params)
    stored, problems = read_plot_file(tmp_path, "scf")
    fresh = ScfParams()
    assert problems == [] and apply_stored(fresh, stored, SCF.param_schema(plain)) == []
    assert asdict(fresh) == asdict(params)
    # No schema field without spin: the dataclass still says the stored value must be a color.
    assert apply_stored(ScfParams(), {"magnetization_color": "nope"}, SCF.param_schema(plain)) == [
        "magnetization_color"
    ]


def test_apply_limits_keeps_the_iteration_range_only():
    params = ScfParams()
    SCF.apply_limits(params, [((1.0, 4.0), (1e-9, 1e-2)), ((1.0, 4.0), (0.0, 1.0))])
    assert (params.xmin, params.xmax) == (1.0, 4.0)
    SCF.apply_limits(params, [])  # an empty figure has nothing to store
    assert (params.xmin, params.xmax) == (1.0, 4.0)


# -- figure --------------------------------------------------------------------------------------
def test_panels_with_and_without_spin(tmp_path):
    _r, plain, params = load(write(tmp_path, synthetic(4)))
    figure, info = render(plain, params)
    accuracy, energy = figure.axes
    assert accuracy.get_yscale() == energy.get_yscale() == "log"
    assert accuracy.get_ylabel() == "Precisão estimada (Ry)" and energy.get_ylabel() == "|ΔE| (Ry)"
    assert energy.get_xlabel() == "Iteração SCF"
    assert [t.get_text() for t in accuracy.get_legend().get_texts()] == ["conv_thr = 1.0e-08 Ry"]
    assert info.xlim == tuple(accuracy.get_xlim()) == (0.5, 4.5)
    assert info.summary.startswith("Convergiu ✓ em 4 iterações")

    _r, spin, params = load(write(tmp_path, synthetic(4, spin=True), "spin.out"))
    figure, _info = render(spin, params)
    assert len(figure.axes) == 3
    magnetization = figure.axes[2]
    assert magnetization.get_ylabel() == "Magnetização (μB/célula)"
    assert [t.get_text() for t in magnetization.get_legend().get_texts()] == ["total", "absoluta"]
    params.show_magnetization = False
    assert len(render(spin, params)[0].axes) == 2


def test_threshold_line_and_scale_options(tmp_path):
    _r, dataset, params = load(write(tmp_path, synthetic(4)))
    figure, _info = render(dataset, params)
    assert len(figure.axes[0].get_lines()) == 2  # data + conv_thr
    params.show_threshold = False
    figure, _info = render(dataset, params)
    assert len(figure.axes[0].get_lines()) == 1 and figure.axes[0].get_legend() is None
    params.scale, params.energy_mode = "linear", "total"
    figure, _info = render(dataset, params)
    accuracy, energy = figure.axes
    assert accuracy.get_yscale() == energy.get_yscale() == "linear"
    assert (
        energy.get_ylabel() == "Energia total (Ry)" and len(energy.get_lines()[0].get_xdata()) == 4
    )
    params.xmin, params.xmax = 2.0, 3.0
    assert render(dataset, params)[1].xlim == (2.0, 3.0)


def test_log_scale_with_a_zero_delta_does_not_warn(tmp_path):
    _r, dataset, params = load(write(tmp_path, synthetic(4, flat=True)))
    assert set(dataset.data.energy_deltas) == {0.0}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        figure, _info = render(dataset, params)
    assert figure.axes[1].get_yscale() == "log"


def test_one_iteration_draws_the_empty_energy_panel(tmp_path):
    _r, dataset, params = load(write(tmp_path, synthetic(1)))
    figure, _info = render(dataset, params)
    accuracy, energy = figure.axes
    assert accuracy.axison and not energy.axison and energy.texts[0].get_text() == NO_DELTAS


def test_no_panel_selected_draws_only_the_message(tmp_path):
    _r, dataset, params = load(write(tmp_path, synthetic(3)))
    params.show_accuracy = params.show_energy = False
    figure, info = render(dataset, params)
    assert figure.axes == [] and [t.get_text() for t in figure.texts] == [NO_PANELS]
    assert info.summary.startswith("Convergiu ✓")


def test_ticks_are_integers_and_thinned_above_twenty(tmp_path):
    _r, dataset, params = load(write(tmp_path, synthetic(60)))
    figure, _info = render(dataset, params)
    ticks = list(figure.axes[-1].get_xticks())
    assert ticks[0] == 1 and len(ticks) <= 21 and all(t == int(t) for t in ticks)


def test_summaries(tmp_path):
    _r, dataset, _p = load(AL)
    assert SCF.summary(dataset) == (
        "Convergiu ✓ em 4 iterações · precisão 3.7e-09 Ry (limiar 1.0e-08) · E = -5.03855495 Ry"
    )
    _r, one, _p = load(write(tmp_path, synthetic(1)))
    assert SCF.summary(one).startswith("Convergiu ✓ em 1 iteração ·")


# -- performance (NFR §7: < 500 ms) --------------------------------------------------------------
@pytest.mark.perf
def test_two_hundred_iterations_load_and_render_under_budget(tmp_path):
    path = write(tmp_path, synthetic(200, spin=True, filler=300))  # ~65k lines
    start = time.perf_counter()
    _result, dataset, params = load(path)
    render(dataset, params)
    assert len(dataset.data.iterations) == 200
    assert time.perf_counter() - start < 0.5
