import gc
import shutil
import weakref

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QSize
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.calculations.base import Method
from qe_studio.ui.dialogs.overwrite import OverwriteChoice
from qe_studio.ui.widgets.plot_view import PlotView

from conftest import FIXTURES


@pytest.fixture
def no_dialogs(monkeypatch):
    """Fail loudly if a dialog would block; individual tests replace what they expect."""
    calls = {"overwrite": [], "mapping": [], "warning": []}

    def overwrite(parent, existing, new_stem):
        calls["overwrite"].append([p.name for p in existing])
        return OverwriteChoice.NEW_VERSION, False

    def mapping(*args, **kwargs):
        calls["mapping"].append(args)
        return None

    monkeypatch.setattr("qe_studio.ui.main_window.ask_overwrite", overwrite)
    monkeypatch.setattr("qe_studio.ui.main_window.ask_mapping", mapping)
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a[2]))
    )
    return calls


def generate(qtbot, window, folder, auto_export=True):
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=auto_export)
    return blocker.args[0]


def test_generate_bands_exports_to_plots(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    session = generate(qtbot, window, folder)
    view = window.current_plot()
    assert isinstance(view, PlotView) and view.session is session
    assert window.left.currentWidget() is window.params
    assert sorted(p.name for p in (folder / "plots").iterdir()) == [
        "bands.pdf",
        "bands.png",
        "bands.svg",
    ]
    assert "E_F = 8.0584 eV" in window.status.readout.text()
    assert no_dialogs["overwrite"] == []

    written = window.export_plot()  # files exist now: dialog → new version
    assert no_dialogs["overwrite"] == [["bands.png", "bands.svg", "bands.pdf"]]
    assert [p.name for p in written] == ["bands_2.png", "bands_2.svg", "bands_2.pdf"]


def test_overwrite_remembered_for_session(
    qtbot, main_window, demo_project, no_dialogs, monkeypatch
):
    window = main_window
    answers = []
    monkeypatch.setattr(
        "qe_studio.ui.main_window.ask_overwrite",
        lambda *a: answers.append(1) or (OverwriteChoice.OVERWRITE, True),
    )
    generate(qtbot, window, demo_project / "03_bands")
    window.export_plot()
    window.export_plot()
    assert len(answers) == 1
    assert not (demo_project / "03_bands" / "plots" / "bands_2.png").exists()


def test_cancel_export(qtbot, main_window, demo_project, no_dialogs, monkeypatch):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands")
    monkeypatch.setattr(
        "qe_studio.ui.main_window.ask_overwrite", lambda *a: (OverwriteChoice.CANCEL, False)
    )
    assert window.export_plot() == []


def test_params_edit_rerenders(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    view = window.current_plot()
    window.params._set("emin", -3.0)
    qtbot.waitUntil(lambda: view.figure.axes[0].get_ylim()[0] == -3.0, timeout=3000)
    window.params._set("reference", "absolute")  # keeps the absolute window
    assert view.session.params.emin == pytest.approx(-3.0 + 8.0584)
    window.params._set("export_png", False)
    assert view.session.params.export_formats == ["svg", "pdf"]


def test_zoom_limits_flow_into_params(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    view = window.current_plot()
    ax = view.figure.axes[0]
    ax.set_ylim(-2.0, 1.0)
    ax.set_xlim(0.5, 2.0)
    view._on_release(None)
    params = view.session.params
    assert (params.emin, params.emax, params.xmin, params.xmax) == (-2.0, 1.0, 0.5, 2.0)
    view._reset()
    assert (params.emin, params.emax, params.xmin) == (-5.0, 5.0, None)


def test_canvas_keeps_export_inches(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    view = window.current_plot()
    for size in (QSize(900, 700), QSize(500, 900)):
        view.resize(size)
        qtbot.wait(20)
        width, height = view.figure.get_size_inches()
        assert width == pytest.approx(6.0, rel=0.02)
        rect = view.box.target_rect()
        assert rect.width() / rect.height() == pytest.approx(6.0 / 4.5, rel=0.02)


def test_theme_toggle_rerenders_plot(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    window.toggle_theme()
    assert window.current_plot().figure.get_facecolor()[:3] == (1.0, 1.0, 1.0)
    window.toggle_theme()


def test_closed_plot_is_released(qtbot, main_window, demo_project, no_dialogs):
    """A closed tab must not stay connected to the theme (leak, then RuntimeError on toggle)."""
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    ref = weakref.ref(window.current_plot())
    window.workspace.close_tab(window.workspace.tabs.currentIndex())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    assert ref() is None
    window.toggle_theme()
    window.toggle_theme()


def test_pdos_plot(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    session = generate(qtbot, window, demo_project / "04_pdos", auto_export=False)
    assert session.kind == "pdos"
    assert session.result.method is Method.NAME
    window.params._set("grouping", "orbital")
    qtbot.wait(200)
    labels = [ln.get_label() for ln in window.current_plot().figure.axes[0].get_lines()]
    assert "s" in labels and "p" in labels


def test_manual_mapping_when_scf_missing(qtbot, main_window, demo_project, no_dialogs, monkeypatch):
    window = main_window
    folder = demo_project.parent / "odd_run"  # no *scf* sibling to infer from
    folder.mkdir()
    shutil.copy(FIXTURES / "al_bands/bands.dat.gnu", folder / "dados.gnu")
    elsewhere = demo_project.parent / "outside"
    elsewhere.mkdir()
    shutil.copy(FIXTURES / "al_bands/al.scf.out", elsewhere / "run.log")

    def mapping(parent, folder_, modules, results, message):
        assert [r.badge for r in results] == ["BANDS"]
        return "bands", {"scf_out": [elsewhere / "run.log"], "gnu": [folder / "dados.gnu"]}, True

    monkeypatch.setattr("qe_studio.ui.main_window.ask_mapping", mapping)
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.result.methods["scf_out"] is Method.MANUAL
    assert session.dataset.fermi == 8.0584
    assert window.memory.mapping(folder, "bands")["scf_out"] == [elsewhere / "run.log"]


def test_relax_folder_asks_and_can_cancel(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    window.generate_plot_for(demo_project / "01_relax")
    qtbot.waitUntil(lambda: bool(no_dialogs["mapping"]), timeout=5000)
    assert len(no_dialogs["mapping"]) == 1
    message = no_dialogs["mapping"][0][4]
    assert "RELAX" in message
    assert window.current_plot() is None


def test_load_failure_is_reported(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "05_si"
    folder.mkdir()
    for name in ("si.scf.out", "si.band.in", "si.band.out"):
        shutil.copy(FIXTURES / "si_bands" / name, folder / name)
    with qtbot.waitSignal(window.plot_failed, timeout=10_000) as blocker:
        window.generate_plot_for(folder)
    assert "bands.x" in blocker.args[0]
    assert no_dialogs["warning"] and window.current_plot() is None


def test_choose_between_kinds(qtbot, main_window, demo_project, no_dialogs, monkeypatch):
    window = main_window
    folder = demo_project / "03_bands"
    for path in (demo_project / "04_pdos" / "orbitals").iterdir():
        shutil.copy(path, folder / path.name)
    shutil.copy(demo_project / "04_pdos" / "projwfc.out", folder / "projwfc.out")
    offered = []

    def choose(parent, results):
        offered.extend(r.badge for r in results)
        return results[1]

    monkeypatch.setattr("qe_studio.ui.main_window.choose_result", choose)
    session = generate(qtbot, window, folder, auto_export=False)
    assert offered == ["BANDS", "PDOS"] and session.kind == "pdos"


def test_typed_labels_are_remembered(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    generate(qtbot, window, folder, auto_export=False)
    window.params._labels_typed("W, G, X, K, G")
    assert window.memory.labels(folder) == ["W", "G", "X", "K", "G"]
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.labels == "W, G, X, K, G"
