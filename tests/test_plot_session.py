"""Plot sessions and the choice of what to plot, without Qt (spec 15 R5: ``core/plotting/session``
and ``core/detection.plot_choice``)."""

import copy
from pathlib import Path

import pytest

from qe_studio.core.calculations import module_for
from qe_studio.core.calculations.base import DetectionResult
from qe_studio.core.calculations.info import CalcModule
from qe_studio.core.config import AppConfig
from qe_studio.core.detection import (
    Ambiguous,
    Chosen,
    ManualTarget,
    NeedsMapping,
    detect_folder,
    mapping_message,
    plot_choice,
)
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.plotting.export import plan_export
from qe_studio.core.plotting.plot_file import stored_params
from qe_studio.core.plotting.session import PlotSession, build_session, load_plot, target_key
from qe_studio.core.sniff import SniffCache

from conftest import FIXTURES

CONFIG = AppConfig()


@pytest.fixture
def bands():
    (result,) = detect_folder(FIXTURES / "al_bands", sniff=SniffCache().sniff)
    _result, dataset = load_plot(result, SniffCache().sniff)
    return result, dataset


@pytest.fixture
def memory(tmp_path) -> FolderMemory:
    return FolderMemory(tmp_path / "memory.json")


def test_defaults_without_a_plot_file(bands, memory):
    result, dataset = bands
    session, warnings = build_session(result, dataset, CONFIG, (None, []), memory)
    assert session.params == session.defaults and warnings == []
    assert session.key == target_key(result) == f"plot:bands:{FIXTURES / 'al_bands'}"


def test_stored_settings_apply_over_the_defaults(bands, memory):
    result, dataset = bands
    stored = {"emin": -3.0, "background": "#123456"}
    session, warnings = build_session(result, dataset, CONFIG, (stored, ["aviso"]), memory)
    assert (session.params.emin, session.params.background) == (-3.0, "#123456")
    assert session.defaults.emin == -5.0  # "Restaurar padrões" goes back to the module's
    assert warnings == ["aviso"]


def test_a_bad_stored_value_is_dropped(bands, memory, caplog):
    result, dataset = bands
    session, _ = build_session(result, dataset, CONFIG, ({"background": "nope"}, []), memory)
    assert session.params.background == session.defaults.background
    assert "ignored background" in caplog.text


def test_legacy_labels_only_without_a_plot_file(bands, memory):
    result, dataset = bands
    memory.set_labels(result.folder, ["L", "G", "X"])
    legacy, _ = build_session(result, dataset, CONFIG, (None, []), memory)
    assert legacy.params.labels == "L, G, X"
    stored, _ = build_session(result, dataset, CONFIG, ({"labels": ""}, []), memory)
    assert stored.params.labels == ""


def test_the_edits_of_an_open_plot_win_over_its_file(bands, memory):
    result, dataset = bands
    open_session, _ = build_session(result, dataset, CONFIG, (None, []), memory)
    open_session.params.emin = -2.0
    stored = (stored_params(copy.deepcopy(open_session.defaults)), ["bands.plot inválido"])
    session, warnings = build_session(result, dataset, CONFIG, stored, memory, open_session)
    assert session.params.emin == -2.0 and session.defaults.emin == -5.0 and warnings == []
    unedited, _ = build_session(result, dataset, CONFIG, (None, []), memory)
    session, _ = build_session(result, dataset, CONFIG, ({"emin": -4.0}, []), memory, unedited)
    assert session.params.emin == -4.0  # an unedited open plot takes the file


def test_manual_targets_are_matched_by_load_plot(tmp_path):
    folder = tmp_path / "odd"
    folder.mkdir()
    (folder / "dados.gnu").write_bytes((FIXTURES / "al_bands" / "bands.dat.gnu").read_bytes())
    scf = FIXTURES / "al_bands" / "al.scf.out"
    module = module_for("bands")
    sniff = SniffCache().sniff
    target = ManualTarget(module, folder, {"scf_out": [scf], "gnu": [folder / "dados.gnu"]}, sniff)
    assert target.kind == "bands" and target_key(target) == f"plot:bands:{folder}"
    result, dataset = load_plot(target, sniff)
    assert result.files["scf_out"] == [scf] and dataset.fermi == 8.0584


def test_render_info_lands_in_the_session(bands, memory):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    result, dataset = bands
    session = PlotSession(result, dataset, result.module.default_params(CONFIG, dataset))
    figure = Figure()
    FigureCanvasAgg(figure)
    info = session.render(figure, session.style)
    assert session.info is info and "E_F" in info.summary


# -- what "Gerar gráfico" does with the results ------------------------------------------------
def result_of(kind: str, complete: bool = True) -> DetectionResult:
    module = CalcModule() if kind == "calc" else module_for(kind)
    return DetectionResult(module, Path("/sim"), missing=[] if complete else ["gnu"])


def test_one_complete_result_is_chosen():
    bands = result_of("bands")
    assert plot_choice([bands, result_of("calc")]) == Chosen(bands)


def test_several_complete_kinds_are_ambiguous():
    bands, pdos = result_of("bands"), result_of("pdos")
    assert plot_choice([bands, pdos]) == Ambiguous([bands, pdos])


def test_nothing_complete_needs_a_mapping():
    assert plot_choice([result_of("bands", complete=False)]) == NeedsMapping("")
    choice = plot_choice([result_of("calc")])
    assert isinstance(choice, NeedsMapping)
    assert choice.message.startswith("Esta pasta foi identificada como CALC, que não tem gráfico")
    assert plot_choice([]) == NeedsMapping(mapping_message([]))
    assert mapping_message([]).startswith("Nenhum cálculo reconhecido nesta pasta")


# -- export plan --------------------------------------------------------------------------------
def test_export_plan(bands, memory, tmp_path):
    result, dataset = bands
    session, _ = build_session(result, dataset, CONFIG, (None, []), memory)
    session.result = DetectionResult(result.module, tmp_path, result.files, result.methods)
    plan = plan_export(session)
    assert (plan.stem, plan.formats, plan.existing, plan.new_stem, plan.error) == (
        "bands",
        ["png", "svg", "pdf"],
        [],
        None,
        None,
    )
    (tmp_path / "plots").mkdir()
    (tmp_path / "plots" / "bands.svg").write_text("x")
    plan = plan_export(session)
    assert [p.name for p in plan.existing] == ["bands.svg"] and plan.new_stem == "bands_2"
    session.params.export_png = session.params.export_svg = session.params.export_pdf = False
    assert plan_export(session).error == "Selecione ao menos um formato de exportação."
