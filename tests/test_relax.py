"""Spec 6: relaxation progress (relax / vc-relax) parser, module and figure."""

import time
import warnings
from dataclasses import asdict
from pathlib import Path

import matplotlib
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.calculations.params import ordered_sections
from qe_studio.core.calculations.relax import NO_DELTAS, RelaxDataset, RelaxParams
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.relax import CRITERIA, HEADER, INPUT, QE_DEFAULT, parse_relax, read_relax
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES, copy_fixture

CONFIG = AppConfig()
RELAX = module_for("relax")


def load(folder: Path):
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    assert result.kind == "relax"
    dataset = RELAX.load(result)
    return result, dataset, RELAX.default_params(CONFIG, dataset)


def render(dataset, params):
    figure = Figure(figsize=params.figure_size, dpi=80)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context(LIGHT.rc(params.font_size)):
        info = RELAX.render(figure, dataset, params, LIGHT)
    figure.canvas.draw()
    return figure, info


def synthetic(steps: int, thresholds: bool = True, filler: int = 0) -> str:
    """A pw.x relax output with ``steps`` SCFs; the last one is closed by "bfgs converged"."""
    lines = ["     Program PWSCF v.7.3.1 starts on  1Jan2025 at 16: 0: 1", ""]
    if thresholds:
        lines += [
            "     energy convergence thresh.=      1.0E-04",
            "     force convergence thresh. =      1.0E-03",
        ]
    lines.append("         1           Si  tau(   1) = (   0.0000000   0.0000000   0.0000000  )")
    for k in range(steps):
        lines += [f"     k = 0.0 0.0 0.{k}  ( 100 PWs)   bands (ev):"] * filler
        lines += [
            f"!    total energy              =  {-15.8 - 0.05 * (1 - 0.5**k):.8f} Ry",
            f"     Total force =     {0.2 * 0.5**k:.6f}     Total SCF correction =     0.000000",
            f"     number of scf cycles    =   {k + 1}",
        ]
        if k < steps - 1:
            lines.append(f"     number of bfgs steps    =   {k}")
        else:
            lines.append(f"     bfgs converged in {k + 1:3d} scf cycles and {k:3d} bfgs steps")
    lines.append("   JOB DONE.")
    return "\n".join(lines) + "\n"


# -- parser ------------------------------------------------------------------------------------
def test_si_relax():
    data = read_relax(FIXTURES / "si_relax" / "si.rel.out")
    assert [(s.index, s.bfgs_step) for s in data.steps] == [(i, i) for i in range(7)]
    assert data.steps[-1].scf_cycles == 7  # closed by "bfgs converged in 7 scf cycles …"
    assert (data.energy_threshold, data.force_threshold) == (1e-4, 1e-6)
    assert data.energy_threshold_source == data.force_threshold_source == HEADER
    assert data.converged and data.job_done and data.truncated_steps == 0
    assert data.energy_deltas[-1] == 0.0 and data.final_scf_energy is None
    assert data.calculation == "relax" and data.formula == "Si2"


def test_vc_relax_final_scf_is_not_a_step():
    data = read_relax(FIXTURES / "kao_vc_relax" / "vc-relax.out")
    assert data.calculation == "vc-relax"
    # The fixture keeps the first 3 and the last 2 BFGS steps of the real run.
    assert [s.bfgs_step for s in data.steps] == [0, 1, 2, 23, 24]
    assert [s.index for s in data.steps] == [0, 1, 2, 3, 4]
    assert data.steps[-1].energy_ry == -1107.46419180
    assert data.final_scf_energy == -1107.46420305
    assert (data.energy_threshold, data.force_threshold) == (1e-5, 1e-4)
    assert data.converged and data.job_done and data.truncated_steps == 0
    assert data.formula == "Al4Si4O18H8"


def test_slab_and_single_step_relax():
    slab = read_relax(FIXTURES / "kao_slab_relax" / "relax-kaolinite-slab-001.out")
    assert [s.bfgs_step for s in slab.steps] == [0, 1, 2, 40, 41] and slab.converged
    single = read_relax(FIXTURES / "kao_supercell_relax" / "relax-kaolinite-slab-001-2x1x.out")
    assert [(s.index, s.bfgs_step, s.scf_cycles) for s in single.steps] == [(0, 0, 1)]
    assert single.energy_deltas == [] and single.converged


def test_truncated_output(tmp_path):
    folder = copy_fixture("si_relax", tmp_path)
    out = folder / "si.rel.out"
    lines = out.read_text().splitlines(keepends=True)
    energies = [i for i, line in enumerate(lines) if line.startswith("!")]
    out.write_text("".join(lines[: energies[3] + 3]))  # inside step 3: energy, no force yet
    result, dataset, _params = load(folder)
    data = dataset.data
    assert len(data.steps) == 3 and data.truncated_steps == 1
    assert not data.converged and not data.job_done
    assert "1 passo incompleto ignorado" in dataset.warnings
    assert any("sem JOB DONE" in w for w in dataset.warnings)
    assert RELAX.summary(dataset).startswith("Em andamento · 2 passos BFGS")


def test_threshold_sources():
    data = parse_relax(synthetic(3, thresholds=False).splitlines())
    assert (data.energy_threshold, data.force_threshold) == (1e-4, 1e-3)
    assert data.energy_threshold_source == QE_DEFAULT and data.defaulted_thresholds
    data = parse_relax(synthetic(3, thresholds=False).splitlines(), fallback=(1e-5, None))
    assert (data.energy_threshold, data.energy_threshold_source) == (1e-5, INPUT)
    assert data.force_threshold_source == QE_DEFAULT
    text = synthetic(3, thresholds=False).replace(
        "   JOB DONE.",
        "     (criteria: energy <  2.0E-05 Ry, force <  3.0E-04 Ry/Bohr)\n   JOB DONE.",
    )
    data = parse_relax(text.splitlines(), fallback=(1e-5, 1e-6))
    assert (data.energy_threshold, data.force_threshold) == (2e-5, 3e-4)
    assert data.energy_threshold_source == data.force_threshold_source == CRITERIA


def test_not_relaxed_without_bfgs_convergence():
    text = synthetic(4).replace(
        "bfgs converged in   4 scf cycles and   3 bfgs steps", "number of bfgs steps    =   3"
    )  # e.g. nstep reached: finished, but above the thresholds
    data = parse_relax(text.splitlines())
    assert len(data.steps) == 4 and data.job_done and not data.converged
    assert RELAX.summary(RelaxDataset(Path("run"), data)).startswith("Não relaxado")


def test_failed_bfgs_closes_the_last_step():
    text = synthetic(4).replace(
        "bfgs converged in   4 scf cycles and   3 bfgs steps",
        "bfgs failed after   4 scf cycles and   3 bfgs steps, convergence not achieved",
    )  # real pw.x wording after "history already reset at previous step: exiting"
    data = parse_relax(text.splitlines())
    assert [s.bfgs_step for s in data.steps] == [0, 1, 2, 3] and data.truncated_steps == 0
    assert data.job_done and not data.converged


# -- module --------------------------------------------------------------------------------------
def test_detected_and_loaded_with_input_thresholds(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "relax.out").write_text(synthetic(3, thresholds=False))
    (folder / "relax.in").write_text(
        " &CONTROL\n  calculation = 'relax'\n  etot_conv_thr = 1.0d-5\n /\n &SYSTEM\n  ibrav = 2\n /\n"
    )
    result, dataset, _params = load(folder)
    assert result.plottable and result.file("relax_in") == folder / "relax.in"
    assert (
        dataset.data.energy_threshold == 1e-5 and dataset.data.force_threshold_source == QE_DEFAULT
    )
    assert "limiares de convergência não encontrados: padrões do QE" in dataset.warnings


def test_no_complete_step_is_a_load_error(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    text = synthetic(1).split("     Total force")[0]  # energy only
    (folder / "relax.out").write_text(text + "     number of bfgs steps    =   0\n")
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    with pytest.raises(LoadError, match="Nenhum passo de relaxamento completo em relax.out"):
        RELAX.load(result)


@pytest.mark.parametrize(
    "name", ["si_relax", "kao_vc_relax", "kao_slab_relax", "kao_supercell_relax"]
)
def test_fixtures_are_plottable_relaxations(name):
    (result,) = detect_folder(FIXTURES / name, sniff=SniffCache().sniff)
    assert result.badge == "RELAX" and result.plottable


def test_params_schema_and_export_stem():
    _result, dataset, params = load(FIXTURES / "si_relax")
    assert params.show_legend and (params.panels, params.scale) == ("both", "log")
    assert params.figure_height == pytest.approx(CONFIG.plot.figure_size[1] * 1.5)
    schema = RELAX.param_schema(dataset)
    assert {f.name for f in schema if f.section == "Relaxamento"} == {
        "panels",
        "scale",
        "show_thresholds",
    }
    names = [section.name for section in ordered_sections(RELAX)]
    assert names.index("Relaxamento") < names.index("Eixo X") < names.index("Estilo")
    stems = {}
    for panels in ("both", "energy", "force"):
        params.panels = panels
        stems[panels] = RELAX.export_stem(params)
    assert stems == {"both": "relax", "energy": "relax_energia", "force": "relax_forca"}
    assert module_for("bands").export_stem(None) == "bands"


def test_relax_plot_file_round_trip(tmp_path):
    params = RelaxParams(panels="force", scale="linear", xmin=1.0, energy_color="#123456")
    write_plot_file(tmp_path, "relax", params)
    stored, warnings_ = read_plot_file(tmp_path, "relax")
    fresh = RelaxParams()
    assert warnings_ == [] and apply_stored(fresh, stored, RELAX.param_schema(None)) == []
    assert asdict(fresh) == asdict(params)


def test_summaries():
    _r, si, _p = load(FIXTURES / "si_relax")
    assert RELAX.summary(si) == (
        "Relaxado ✓ · 6 passos BFGS · |ΔE| final 0.0e+00 Ry · F final 0.0e+00 Ry/Bohr"
    )
    _r, vc, _p = load(FIXTURES / "kao_vc_relax")
    assert "24 passos BFGS" in RELAX.summary(vc)
    assert RELAX.summary(vc).endswith("E final (SCF final) -1107.464203 Ry")
    _r, single, _p = load(FIXTURES / "kao_supercell_relax")
    assert RELAX.summary(single) == "Relaxado ✓ · 0 passos BFGS · F final 4.4e-04 Ry/Bohr"


# -- figure --------------------------------------------------------------------------------------
def visible_axes(figure):
    return [ax for ax in figure.axes if ax.axison]


def test_render_panels_and_thresholds():
    _result, dataset, params = load(FIXTURES / "si_relax")
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # log scale with |ΔE| = 0 must not warn
        figure, info = render(dataset, params)
    energy, force = figure.axes
    assert energy.get_yscale() == force.get_yscale() == "log"
    assert len(energy.patches) == 6 and len(force.get_lines()) == 2  # data + threshold
    assert energy.get_ylabel() == "|ΔE| (Ry)" and force.get_xlabel() == "Passo BFGS"
    labels = [t.get_text() for ax in figure.axes for t in ax.get_legend().get_texts()]
    assert labels == ["etot_conv_thr = 1.0e-04 Ry", "forc_conv_thr = 1.0e-06 Ry/Bohr"]
    assert info.xlim == tuple(energy.get_xlim()) == (-0.5, 6.5)
    assert info.ylim == tuple(energy.get_ylim())  # a plain click is not a zoom

    params.show_thresholds = False
    figure, _info = render(dataset, params)
    assert [len(ax.get_lines()) for ax in figure.axes] == [0, 1]
    for panels, ylabel in (("energy", "|ΔE| (Ry)"), ("force", "Força total (Ry/Bohr)")):
        params.panels = panels
        figure, info = render(dataset, params)
        assert len(figure.axes) == 1 and figure.axes[0].get_ylabel() == ylabel
    assert info.xlim == (-0.5, 6.5)
    params.panels, params.scale, params.xmin, params.xmax = "energy", "linear", 2.0, 5.0
    figure, info = render(dataset, params)
    assert figure.axes[0].get_yscale() == "linear" and info.xlim == (2.0, 5.0)


def test_default_thresholds_are_labelled(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "relax.out").write_text(synthetic(3, thresholds=False))
    _result, dataset, params = load(folder)
    figure, _info = render(dataset, params)
    labels = [t.get_text() for ax in figure.axes for t in ax.get_legend().get_texts()]
    assert labels[0] == "etot_conv_thr = 1.0e-04 Ry (padrão do QE)"


def test_single_step_draws_the_empty_energy_panel():
    _result, dataset, params = load(FIXTURES / "kao_supercell_relax")
    figure, _info = render(dataset, params)
    energy, force = figure.axes
    assert not energy.axison and energy.texts[0].get_text() == NO_DELTAS
    assert force.axison and len(force.get_lines()[0].get_xdata()) == 1


# -- performance (NFR §7: < 500 ms) --------------------------------------------------------------
@pytest.mark.perf
def test_hundred_steps_load_and_render_under_budget(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "relax.out").write_text(synthetic(100, filler=800))  # ~80k lines
    start = time.perf_counter()
    _result, dataset, params = load(folder)
    render(dataset, params)
    assert len(dataset.data.steps) == 100
    assert time.perf_counter() - start < 0.5
