"""Spec 6: relaxation progress (relax / vc-relax) parser, module and figure."""

import re
import time
import warnings
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.base import LoadError
from qe_studio.core.calculations.params import ordered_sections
from qe_studio.core.calculations.relax import (
    NO_DELTAS,
    NO_ENTHALPY,
    RelaxDataset,
    RelaxParams,
    input_settings,
)
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import detect_folder
from qe_studio.core.plotting.plot_file import apply_stored, read_plot_file, write_plot_file
from qe_studio.core.plotting.style import LIGHT
from qe_studio.core.qe.relax import (
    BOHR_TO_ANGSTROM,
    CRITERIA,
    HEADER,
    INPUT,
    QE_DEFAULT,
    parse_relax,
    read_relax,
)
from qe_studio.core.sniff import SniffCache, sniff
from test_relax_figures import relax_structure

from conftest import FIXTURES, copy_fixture

CONFIG = AppConfig()
RELAX = module_for("relax")
VC_OUT = FIXTURES / "kao_vc_relax" / "vc-relax.out"


def load(folder: Path):
    (result,) = detect_folder(folder, sniff=SniffCache().sniff)
    assert result.kind == "relax"
    dataset = RELAX.load(result, sniff)
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
        RELAX.load(result, sniff)


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


# -- vc-relax: enthalpy, pressure, volume and cell (spec 27-7) -----------------------------------
def vc_synthetic(
    steps: int = 4, unit: str = "angstrom", without_enthalpy: tuple[int, ...] = (), press: float = 0
) -> str:
    """A vc-relax output in the order pw.x prints it: the energy, force and stress of step k, then
    ``enthalpy new``, the volume and the cell of step k + 1; the last step is closed by
    ``bfgs converged`` and ``Final enthalpy`` and the run ends with the final coordinates.
    Step k has E = -10 - 0.01 k, P = 0.5 - 0.1 k, V = 100 - k Å³ and a cubic cell of side
    ``V ** (1/3)`` (the header volume, of the input cell, is 90 Å³)."""

    def volume(k: int) -> float:
        return 100.0 - k

    def cell(k: int) -> list[str]:
        side = volume(k) ** (1 / 3)
        if unit == "angstrom":
            head, scale = "(angstrom)", 1.0
        elif unit == "bohr":
            head, scale = "(bohr)", 1 / BOHR_TO_ANGSTROM
        else:
            head, scale = "(alat= 10.00000000)", 1 / BOHR_TO_ANGSTROM / 10
        rows = [
            f"   {side * scale:.9f}  0.000000000  0.000000000" if i == 0 else "" for i in range(3)
        ]
        rows[1] = f"   0.000000000  {side * scale:.9f}  0.000000000"
        rows[2] = f"   0.000000000  0.000000000  {side * scale:.9f}"
        return [f"CELL_PARAMETERS {head}", *rows]

    def geometry(k: int) -> list[str]:
        au = volume(k) / BOHR_TO_ANGSTROM**3
        return [
            f"     new unit-cell volume =   {au:.5f} a.u.^3 (   {volume(k):.5f} Ang^3 )",
            "     density =      2.56445 g/cm^3",
            "",
            *cell(k),
            "",
            "ATOMIC_POSITIONS (crystal)",
            "Si            0.0000000000        0.0000000000        0.0000000000",
        ]

    lines = [
        "     Program PWSCF v.7.1 starts on  1Jan2025 at 16: 0: 1",
        "     unit-cell volume          =     607.2 (a.u.)^3",
        "     energy convergence thresh.=      1.0E-05",
        "     force convergence thresh. =      1.0E-04",
        "     press convergence thresh. =      5.0E-01",
        "         1           Si  tau(   1) = (   0.0000000   0.0000000   0.0000000  )",
    ]
    for k in range(steps):
        lines += [
            f"!    total energy              =  {-10 - 0.01 * k:.8f} Ry",
            "     Total force =     0.000100     Total SCF correction =     0.000000",
            "     Computing stress (Cartesian axis) and pressure",
            f"          total   stress  (Ry/bohr**3)                   (kbar)     P=     {0.5 - 0.1 * k:.2f}",
            "   0.00000000   0.00000000   0.00000000            0.00        0.00        0.00",
            f"     number of scf cycles    =   {k + 1}",
        ]
        enthalpy = -10 - 0.01 * k + press * volume(k) * 4.5875e-5
        if k < steps - 1:
            lines.append(f"     number of bfgs steps    =   {k}")
            if k not in without_enthalpy:
                lines.append(f"     enthalpy           new  =   {enthalpy:.10f} Ry")
            lines += geometry(k + 1)
        else:
            lines.append(f"     bfgs converged in {k + 1:3d} scf cycles and {k:3d} bfgs steps")
            lines.append(
                "     (criteria: energy <  1.0E-05 Ry, force <  1.0E-04 Ry/Bohr, cell <  2.0E-01 kbar)"
            )
            lines += [
                f"     Final enthalpy           =   {enthalpy:.10f} Ry",
                "Begin final coordinates",
            ]
            lines += geometry(k) + ["End final coordinates"]
    lines += ["     Final scf calculation at the relaxed structure.", "   JOB DONE."]
    return "\n".join(lines) + "\n"


def vc_steps(**kwargs):
    return parse_relax(vc_synthetic(**kwargs).splitlines()).steps


def test_vc_relax_fixture_has_the_lines_the_parser_reads():
    text = VC_OUT.read_text()
    counts = {
        pattern: len(re.findall(pattern, text, re.M))
        for pattern in (
            r"enthalpy\s+new\s+=",
            r"new unit-cell volume",
            r"total\s+stress.*P=",
            r"^CELL_PARAMETERS",
            r"Final enthalpy",
            r"Final scf calculation",
        )
    }
    assert list(counts.values()) == [
        4,
        5,
        6,
        5,
        1,
        1,
    ]  # 4 + the final coordinates; 5 steps + final SCF


def test_vc_relax_fixture_steps():
    data = read_relax(VC_OUT)
    steps = data.steps
    # Step 0 prints "enthalpy new" without an "old" one and the last step "Final enthalpy".
    assert [s.enthalpy_ry for s in steps] == [
        -1107.4641235902,
        -1107.4641300592,
        -1107.4641359277,
        -1107.4641912450,
        -1107.4641917963,
    ]
    assert [s.pressure_kbar for s in steps] == [-0.13, -0.54, -0.05, 0.01, 0.03]
    # Where the QE prints no enthalpy, E + press·V is the enthalpy: here press = 0.
    assert all(abs(s.enthalpy_ry - s.energy_ry) < 1e-5 for s in steps)
    # The volume and cell the run printed after step k are the geometry of step k + 1: step 0 never
    # has one (the header volume is the input cell, wrong after a restart, as in this run) and
    # step 3 (BFGS step 23) follows a block the fixture trimmed.
    assert [s.volume_ang3 for s in steps] == [None, 334.32919, 334.26610, None, 334.00060]
    assert steps[0].cell is None and steps[3].cell is None
    assert steps[1].cell == (
        (5.189759515, -0.001785998, -0.002133947),
        (0.028833258, 9.008093136, 0.017992089),
        (-1.934884403, -0.228398530, 7.151781276),
    )
    assert data.calculation == "vc-relax" and data.has_pressure and data.has_volume


def test_vc_relax_last_step_cell_is_the_final_coordinates():
    lines = VC_OUT.read_text().splitlines()
    begin = next(i for i, line in enumerate(lines) if line.startswith("Begin final coordinates"))
    header = next(i for i in range(begin, len(lines)) if lines[i].startswith("CELL_PARAMETERS"))
    final = tuple(tuple(float(v) for v in lines[header + k].split()) for k in (1, 2, 3))
    assert read_relax(VC_OUT).steps[-1].cell == final


def test_vc_relax_pressure_threshold_sources():
    data = read_relax(VC_OUT)
    assert (data.pressure_threshold, data.pressure_threshold_source) == (0.5, HEADER)
    assert data.target_pressure_kbar == 0.0
    assert not data.defaulted_thresholds  # the pressure never adds the "padrões do QE" warning
    text = vc_synthetic().splitlines()
    no_header = [line for line in text if "press convergence" not in line]
    data = parse_relax(no_header)
    assert (data.pressure_threshold, data.pressure_threshold_source) == (0.2, CRITERIA)
    no_criteria = [line for line in no_header if "criteria" not in line]
    data = parse_relax(no_criteria, press_conv_thr=3.0, target_pressure=50.0)
    assert (data.pressure_threshold, data.pressure_threshold_source) == (3.0, INPUT)
    assert data.target_pressure_kbar == 50.0
    data = parse_relax(no_criteria)
    assert (data.pressure_threshold, data.pressure_threshold_source) == (0.5, QE_DEFAULT)


def test_vc_relax_attributes_each_value_to_its_geometry():
    steps = vc_steps(steps=4)
    assert [s.volume_ang3 for s in steps] == [None, 99.0, 98.0, 97.0]
    assert [s.pressure_kbar for s in steps] == [0.5, 0.4, 0.3, 0.2]
    assert steps[1].cell is not None and steps[1].cell[0][0] == pytest.approx(99.0 ** (1 / 3))
    assert steps[3].cell is not None and steps[3].cell[2][2] == pytest.approx(97.0 ** (1 / 3))
    assert steps[0].cell is None


@pytest.mark.parametrize("unit", ["bohr", "alat"])
def test_cell_units_give_the_same_cell_in_angstrom(unit):
    reference = vc_steps(unit="angstrom")
    steps = vc_steps(unit=unit)
    for ours, theirs in zip(steps, reference, strict=True):
        assert (ours.cell is None) == (theirs.cell is None)
        if ours.cell is not None and theirs.cell is not None:
            for row, expected in zip(ours.cell, theirs.cell, strict=True):
                assert row == pytest.approx(expected, abs=1e-8)


def test_vc_relax_enthalpy_includes_the_target_pressure():
    data = parse_relax(vc_synthetic(press=50.0).splitlines(), target_pressure=50.0)
    for step in data.steps[1:]:  # V is known from step 1 on
        assert step.volume_ang3 is not None and step.enthalpy_ry is not None
        expected = step.energy_ry + 50.0 * step.volume_ang3 * 4.5875e-5  # 1 kbar·Å³ = 4.5875e-5 Ry
        assert step.enthalpy_ry == pytest.approx(expected, abs=1e-5)
    assert data.target_pressure_kbar == 50.0
    # |ΔH| is the BFGS criterion, not |ΔE|: the volume changes, so they differ.
    (first, enthalpy), (_, _), (_, _) = data.convergence_deltas()
    assert enthalpy and first != pytest.approx(data.energy_deltas[0], abs=1e-9)


def test_unrelated_runs_get_none_of_the_new_fields():
    for name in ("si_relax", "kao_slab_relax", "kao_supercell_relax"):
        (out,) = [p for p in (FIXTURES / name).glob("*.out")]
        data = read_relax(out)
        assert data.calculation == "relax" and not data.has_pressure and not data.has_volume
        assert all(
            s.enthalpy_ry is None and s.pressure_kbar is None and s.volume_ang3 is None
            for s in data.steps
        )
        assert all(s.cell is None for s in data.steps)
        assert data.pressure_threshold_source == QE_DEFAULT and data.target_pressure_kbar == 0.0
        assert data.convergence_deltas() == [(d, False) for d in data.energy_deltas]


def test_vc_relax_cut_anywhere_never_raises_and_keeps_a_prefix():
    lines = VC_OUT.read_text().splitlines(keepends=True)
    full = parse_relax(lines).steps
    for cut in range(0, len(lines) + 1, 11):
        steps = parse_relax(lines[:cut]).steps
        for ours, theirs in zip(steps, full, strict=False):
            # The enthalpy line comes after the step closed: a cut right there leaves it out.
            assert replace(ours, enthalpy_ry=theirs.enthalpy_ry) == theirs
    for cut in range(len(lines) - 1, len(lines) - 8, -1):  # the last lines, one by one
        parse_relax(lines[:cut])


def test_garbled_cell_rows_leave_only_the_cell_out():
    lines = VC_OUT.read_text().splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if line.startswith("CELL_PARAMETERS"))
    lines[first + 2] = "   not a cell row\n"
    steps = parse_relax(lines).steps
    assert steps[1].cell is None and steps[1].volume_ang3 == 334.32919
    assert steps[2].cell is not None and steps[2].volume_ang3 == 334.26610


def test_input_settings_read_the_cell_pressure(tmp_path):
    (tmp_path / "vc.in").write_text(
        " &CONTROL\n  calculation = 'vc-relax'\n  etot_conv_thr = 1.0d-5\n /\n"
        " &CELL\n  press = 50.0d0\n  press_conv_thr = 0.2\n /\n"
    )
    settings = input_settings(tmp_path / "vc.in")
    assert settings.thresholds == (1e-5, None)
    assert (settings.press, settings.press_conv_thr) == (50.0, 0.2)
    assert input_settings(None) == input_settings(tmp_path / "missing.in")
    assert input_settings(None).press is None


def test_target_pressure_of_the_input_reaches_the_figure(tmp_path):
    folder = copy_fixture("kao_vc_relax", tmp_path)
    text = (folder / "vc-relax.in").read_text().replace("&cell\n", "&cell\n  press = 50.0\n")
    (folder / "vc-relax.in").write_text(text)
    _result, dataset, params = load(folder)
    assert dataset.data.target_pressure_kbar == 50.0
    params.panels = "all"
    figure, _info = render(dataset, params)
    low, high = figure.axes[2].get_ylim()  # the band 50 ± 0.5 kbar
    assert low < 49.5 and high > 50.5


# -- vc-relax figure ------------------------------------------------------------------------------
def test_vc_relax_energy_panel_is_the_enthalpy():
    _result, dataset, params = load(FIXTURES / "kao_vc_relax")
    figure, info = render(dataset, params)
    energy, force = figure.axes
    assert energy.get_ylabel() == "|ΔH| (Ry)" and force.get_ylabel() == "Força total (Ry/Bohr)"
    heights = [p.get_height() for p in energy.patches]
    assert heights == pytest.approx([d for d, _ in dataset.data.enthalpy_deltas()], rel=1e-9)
    assert [t.get_text() for t in energy.get_legend().get_texts()] == ["etot_conv_thr = 1.0e-05 Ry"]
    assert info.notes == () and "|ΔH| final 5.5e-07 Ry" in info.summary


def test_all_panels_of_a_vc_relax():
    _result, dataset, params = load(FIXTURES / "kao_vc_relax")
    params.panels = "all"
    figure, info = render(dataset, params)
    energy, force, pressure, volume = figure.axes
    assert [ax.get_ylabel() for ax in figure.axes] == [
        "|ΔH| (Ry)",
        "Força total (Ry/Bohr)",
        "Pressão (kbar)",
        "Volume (Å³)",
    ]
    assert (energy.get_yscale(), force.get_yscale()) == ("log", "log")
    assert pressure.get_yscale() == volume.get_yscale() == "linear"  # `scale` is for energy / force
    data_line, *band = pressure.get_lines()
    assert list(data_line.get_ydata()) == [-0.13, -0.54, -0.05, 0.01, 0.03]
    assert sorted(line.get_ydata()[0] for line in band) == [-0.5, 0.5]  # target 0 ± press_conv_thr
    assert [t.get_text() for t in pressure.get_legend().get_texts()] == [
        "press_conv_thr = 5.0e-01 kbar"
    ]
    (volume_line,) = volume.get_lines()
    assert list(volume_line.get_xdata()) == [1, 2, 4]  # the steps whose geometry the run printed
    assert list(volume_line.get_ydata()) == [334.32919, 334.2661, 334.0006]
    assert volume.get_legend() is None and info.xlim == (-0.5, 4.5)
    assert volume.get_xlabel() == "Passo BFGS" and not pressure.get_xlabel()


def test_all_panels_colors_thresholds_and_scale():
    _result, dataset, params = load(FIXTURES / "kao_vc_relax")
    params.panels, params.scale, params.show_thresholds = "all", "linear", False
    params.pressure_color, params.volume_color = "#123456", "#654321"
    figure, _info = render(dataset, params)
    energy, _force, pressure, volume = figure.axes
    assert energy.get_yscale() == "linear" and energy.get_legend() is None
    assert [line.get_color() for line in pressure.get_lines()] == ["#123456"]
    assert [line.get_color() for line in volume.get_lines()] == ["#654321"]


def test_all_falls_back_to_both_without_cell_data():
    _result, dataset, params = load(FIXTURES / "si_relax")
    figure, info = render(dataset, params)
    both = (relax_structure(figure), info.summary)
    params.panels = "all"
    figure, info = render(dataset, params)
    assert len(figure.axes) == 2 and (relax_structure(figure), info.summary) == both
    assert RELAX.panels_shown(params, dataset.data) == ["energy", "force"]
    assert RELAX.export_stem(params) == "relax_todos"


def test_a_step_without_enthalpy_falls_back_to_the_energy(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "vc-relax.out").write_text(vc_synthetic(steps=5, without_enthalpy=(1,)))
    _result, dataset, params = load(folder)
    data = dataset.data
    assert [h for _, h in data.convergence_deltas()] == [False, False, True, True]  # pairs 0-1, 1-2
    assert data.convergence_deltas()[0][0] == pytest.approx(data.energy_deltas[0])
    figure, info = render(dataset, params)
    assert figure.axes[0].get_ylabel() == "|ΔH| (Ry)" and info.notes == (NO_ENTHALPY,)
    assert "|ΔH| final" in info.summary


def test_a_relax_without_enthalpy_has_no_note():
    _result, dataset, params = load(FIXTURES / "si_relax")
    assert render(dataset, params)[1].notes == ()


def test_vc_relax_readout_of_each_panel():
    _result, dataset, params = load(FIXTURES / "kao_vc_relax")
    params.panels = "all"
    read = lambda x, axes: RELAX.format_coordinates(x, 0.0, axes, dataset, params)  # noqa: E731
    assert read(1.2, 0).startswith("passo 1 · |ΔH| = ") and read(0.0, 0) == ""
    assert read(3.0, 1) == "passo 3 · F = 5.5e-04 Ry/Bohr"
    assert read(4.0, 2) == "passo 4 · P = 0.03 kbar"
    assert read(2.0, 3) == "passo 2 · V = 334.27 Å³"
    assert read(3.0, 3) == ""  # the geometry of step 3 is not in the output
    assert read(9.0, 2) == "" and read(2.0, 4) == ""


def test_vc_relax_summary_has_volume_and_pressure():
    _r, vc, _p = load(FIXTURES / "kao_vc_relax")
    text = RELAX.summary(vc)
    assert "|ΔH| final 5.5e-07 Ry" in text and "V: 334.3 → 334.0 Å³" in text
    assert "P final = 0.03 kbar" in text and text.endswith("E final (SCF final) -1107.464203 Ry")


def test_vc_relax_params_round_trip(tmp_path):
    params = RelaxParams(panels="all", pressure_color="#123456", volume_color="#abcdef")
    write_plot_file(tmp_path, "relax", params)
    stored, warnings_ = read_plot_file(tmp_path, "relax")
    fresh = RelaxParams()
    assert warnings_ == [] and apply_stored(fresh, stored, RELAX.param_schema(None)) == []
    assert asdict(fresh) == asdict(params)
    schema = {f.name: f for f in RELAX.param_schema(None)}
    assert schema["pressure_color"].section == schema["volume_color"].section == "Estilo"
    assert [value for value, _ in schema["panels"].choices] == ["both", "energy", "force", "all"]


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
