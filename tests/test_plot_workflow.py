import gc
import os
import shutil
import threading
import weakref

import pytest
import yaml
from matplotlib.colors import to_hex
from matplotlib.image import imread
from PyQt6.QtCore import QCoreApplication, QEvent, QSize
from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QLabel, QMessageBox, QPushButton

from qe_studio.core import detection as detection_module
from qe_studio.core.calculations.base import Method
from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.ui.dialogs.overwrite import OverwriteChoice
from qe_studio.ui.widgets.param_widgets import Section, SeriesList
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

    monkeypatch.setattr("qe_studio.ui.plot_export.ask_overwrite", overwrite)
    monkeypatch.setattr("qe_studio.ui.plot_workflow.ask_mapping", mapping)
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: calls["warning"].append(a[2]))
    )
    return calls


def generate(qtbot, window, folder, auto_export=True):
    """Plot ``folder``; with ``auto_export``, also wait for the files (written in a worker)."""
    signals = [window.plot_ready, window.export_finished] if auto_export else [window.plot_ready]
    with qtbot.waitSignals(signals, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=auto_export)
    return next(e.args[0] for e in blocker.all_signals_and_args if "plot_ready" in e.signal_name)


def export(qtbot, window) -> list:
    """Ctrl+E and wait for the worker: the written paths."""
    with qtbot.waitSignal(window.export_finished, timeout=10_000) as blocker:
        assert window.export_plot()
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
    assert to_hex(imread(folder / "plots" / "bands.png")[0, 0]) == "#ffffff"  # dark app theme

    written = export(qtbot, window)  # files exist now: dialog → new version
    assert no_dialogs["overwrite"] == [["bands.png", "bands.svg", "bands.pdf"]]
    assert [p.name for p in written] == ["bands_2.png", "bands_2.svg", "bands_2.pdf"]


def test_overwrite_remembered_for_session(
    qtbot, main_window, demo_project, no_dialogs, monkeypatch
):
    window = main_window
    answers = []
    monkeypatch.setattr(
        "qe_studio.ui.plot_export.ask_overwrite",
        lambda *a: answers.append(1) or (OverwriteChoice.OVERWRITE, True),
    )
    generate(qtbot, window, demo_project / "03_bands")
    export(qtbot, window)
    export(qtbot, window)
    assert len(answers) == 1
    assert not (demo_project / "03_bands" / "plots" / "bands_2.png").exists()


def test_cancel_export(qtbot, main_window, demo_project, no_dialogs, monkeypatch):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands")
    monkeypatch.setattr(
        "qe_studio.ui.plot_export.ask_overwrite", lambda *a: (OverwriteChoice.CANCEL, False)
    )
    assert window.export_plot() is False


def test_params_edit_rerenders(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    view = window.current_plot()
    window.params.set_param("emin", -3.0)
    qtbot.waitUntil(lambda: view.figure.axes[0].get_ylim()[0] == -3.0, timeout=3000)
    window.params.set_param("reference", "absolute")  # keeps the absolute window
    assert view.session.params.emin == pytest.approx(-3.0 + 8.0584)
    window.params.set_param("export_png", False)
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


def test_back_and_forward_flow_into_params(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    view = window.current_plot()
    nav, ax = view.toolbar.nav, view.figure.axes[0]
    nav.push_current()  # what a toolbar zoom records: the first view, then the zoomed one
    ax.set_ylim(-2.0, 1.0)
    nav.push_current()
    view._on_release(None)
    params = view.session.params
    assert (params.emin, params.emax) == (-2.0, 1.0)
    view.toolbar.back.click()
    assert (params.emin, params.emax) == pytest.approx((-5.0, 5.0))
    view.toolbar.forward.click()
    assert (params.emin, params.emax) == (-2.0, 1.0)


def test_regenerate_keeps_edits_made_while_loading(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    session = generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    session.params.emin = -3.0  # edited after the worker read bands.plot (none yet)
    window.plot_workflow.show_loaded(session.result, session.dataset, (None, []))
    new = window.current_plot().session
    assert new is not session and new.params.emin == -3.0 and new.defaults.emin == -5.0


def test_detected_results_survive_an_invalidation(qtbot, main_window, demo_project, no_dialogs):
    """A refresh or sync between detection and the next loop turn must not lose the results."""
    window = main_window
    folder = demo_project / "03_bands"
    window.service.detect_now(folder)
    window.plot_workflow._detecting[str(folder)] = False
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.plot_workflow._on_detected(str(folder))
        window.service.invalidate()
    assert no_dialogs["mapping"] == []


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


def test_figure_stays_white_whatever_the_theme(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    assert window.theme.name == "dark"
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    figure = window.current_plot().figure
    assert to_hex(figure.get_facecolor()) == "#ffffff"
    window.toggle_theme()
    assert to_hex(figure.get_facecolor()) == "#ffffff"
    window.toggle_theme()
    assert to_hex(figure.get_facecolor()) == "#ffffff"


@pytest.mark.parametrize("folder", ["03_bands", "04_pdos"])
def test_background_parameter_rerenders(qtbot, main_window, demo_project, no_dialogs, folder):
    window = main_window
    generate(qtbot, window, demo_project / folder, auto_export=False)
    labels = [label.text() for label in window.params.body.findChildren(QLabel)]
    assert "Cor de fundo" in labels and "background" in window.params.body._setters
    figure = window.current_plot().figure
    window.params.set_param("background", "#123456")
    qtbot.waitUntil(lambda: to_hex(figure.get_facecolor()) == "#123456", timeout=3000)
    assert to_hex(figure.axes[0].get_facecolor()) == "#123456"


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
    window.params.set_param("grouping", "orbital")
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

    monkeypatch.setattr("qe_studio.ui.plot_workflow.ask_mapping", mapping)
    on_gui_thread = []
    real = detection_module.manual_result

    def manual_result(*args):
        on_gui_thread.append(threading.current_thread() is threading.main_thread())
        return real(*args)

    monkeypatch.setattr(detection_module, "manual_result", manual_result)
    session = generate(qtbot, window, folder, auto_export=False)
    assert on_gui_thread == [False]  # it sniffs the mapped files: load worker only
    assert session.result.methods["scf_out"] is Method.MANUAL
    assert session.dataset.fermi == 8.0584
    assert window.memory.mapping(folder, "bands")["scf_out"] == [elsewhere / "run.log"]


def test_relax_plot(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "01_relax"
    session = generate(qtbot, window, folder)
    assert no_dialogs["mapping"] == []  # plottable now: no manual mapping
    tabs = window.workspace.tabs
    assert tabs.tabText(tabs.currentIndex()) == "Otimização estrutural · 01_relax"
    assert sorted(p.name for p in (folder / "plots").iterdir()) == [
        "relax.pdf",
        "relax.png",
        "relax.svg",
    ]
    assert window.status.readout.text().startswith("01_relax · Relaxado ✓ · 6 passos BFGS")
    window.params.set_param("panels", "energy")
    assert [p.name for p in export(qtbot, window)] == [
        "relax_energia.png",
        "relax_energia.svg",
        "relax_energia.pdf",
    ]
    # toolbar zoom of the two stacked panels: only the step range of the first is kept
    session.apply_limits([((1.0, 4.0), (1e-6, 1e-2)), ((1.0, 4.0), (0.0, 1.0))])
    assert (session.params.xmin, session.params.xmax) == (1.0, 4.0)
    session.reset_view()
    assert (session.params.xmin, session.params.xmax) == (None, None)


def test_scf_folder_plots_the_convergence_without_a_mapping(
    qtbot, main_window, demo_project, no_dialogs
):
    window = main_window
    folder = demo_project / "02_scf"
    session = generate(qtbot, window, folder)  # "Gerar Gráfico" saves, as for any plot
    assert session.kind == "scf" and no_dialogs["mapping"] == []
    tabs = window.workspace.tabs
    assert tabs.tabText(tabs.currentIndex()) == "Convergência SCF · scf.out"
    assert session.key == f"plot:scf:{folder / 'scf.out'}"
    assert (folder / "plots" / "scf.png").exists()
    assert window.status.readout.text().startswith("scf.out · Convergiu ✓ em 4 iterações")


def test_plot_file_previews_one_output_without_saving(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"  # a bands folder: Ctrl+G would plot the bands
    output = folder / "scf.out"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.plot_file(output, "scf")
    session = blocker.args[0]
    assert session.kind == "scf" and session.result.methods["scf_out"] is Method.MANUAL
    tabs = window.workspace.tabs
    assert tabs.tabText(tabs.currentIndex()) == "Convergência SCF · scf.out"
    assert not (folder / "plots").exists() and no_dialogs["mapping"] == []
    assert window.workspace.isVisible() and window.left.currentWidget() is window.params
    assert window.status.readout.text().startswith("scf.out · Convergiu ✓")

    window.params.set_param("scale", "linear")  # the settings go to <folder>/scf.plot
    window.plot_settings.flush_now()
    stored, _ = read_plot_file(folder, "scf")
    assert stored["scale"] == "linear"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.plot_file(output, "scf")  # again: the same tab, settings read back
    assert window.workspace.keys().count(session.key) == 1
    assert window.current_plot().session.params.scale == "linear"


def test_two_outputs_of_one_folder_get_a_tab_each(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "02_scf"
    shutil.copy(FIXTURES / "al_bands/al.scf.out", folder / "al.scf.out")
    keys = []
    for name in ("scf.out", "al.scf.out"):
        with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
            window.plot_file(folder / name, "scf")
        keys.append(blocker.args[0].key)
    assert len(set(keys)) == 2 and all(window.workspace.widget_for(k) for k in keys)
    assert window.workspace.tabs.tabText(1) == "Convergência SCF · al.scf.out"
    # the one scf.plot of the folder is shared by both
    assert {s.folder for s in (window.workspace.widget_for(k).session for k in keys)} == {folder}


def test_plot_button_is_only_for_an_open_scf_output(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    button = window.top_bar.plot_file
    assert button.text() == "Plotar SCF" and not button.isVisible()  # no tabs
    folder = demo_project / "03_bands"
    window.service.detect_now(folder)
    window.open_file(folder / "scf.out")
    assert button.isVisible()
    window.open_file(folder / "bands.in")  # an input
    assert not button.isVisible()
    window.workspace.set_current(window.workspace.widget_for(str(folder / "scf.out")))
    assert button.isVisible()
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        button.click()
    assert blocker.args[0].kind == "scf" and not button.isVisible()  # now on the plot tab
    assert not (folder / "plots").exists()
    window.workspace.set_current(window.workspace.widget_for(str(folder / "scf.out")))
    assert button.isVisible()
    window.workspace.close_key(str(folder / "scf.out"))  # closing the current tab
    assert not button.isVisible()
    window.workspace.close_key(blocker.args[0].key)
    window.workspace.close_key(str(folder / "bands.in"))
    assert window.workspace.current() is None and not button.isVisible()


def test_plot_button_follows_the_detection_of_a_new_folder(qtbot, main_window, demo_project):
    window = main_window
    folder = demo_project / "02_scf"
    window.service.invalidate(folder)
    window.open_file(folder / "scf.out")
    qtbot.waitUntil(lambda: window.top_bar.plot_file.isVisible(), timeout=5000)


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

    monkeypatch.setattr("qe_studio.ui.plot_workflow.choose_result", choose)
    session = generate(qtbot, window, folder, auto_export=False)
    assert offered == ["BANDS", "PDOS"] and session.kind == "pdos"


def test_typed_labels_are_saved_in_the_plot_file(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    session = generate(qtbot, window, folder, auto_export=False)
    window.params.set_param("labels", "W, G, X, K, G")
    window.workspace.close_key(session.key)  # flushes bands.plot
    assert window.memory.labels(folder) is None  # no longer written to FolderMemory
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.labels == "W, G, X, K, G"


def test_legacy_labels_only_without_plot_file(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    window.memory.set_labels(folder, ["L", "G", "X", "U", "G"])
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.labels == "L, G, X, U, G"
    window.params.set_param("labels", "")
    window.plot_settings.flush_now()
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.labels == ""


def test_plot_settings_persist(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    path = folder / "bands.plot"
    session = generate(qtbot, window, folder, auto_export=False)
    window.plot_settings.flush_now()
    assert not path.exists()  # generating alone never writes
    window.params.set_param("emin", -3.0)
    qtbot.waitUntil(path.exists, timeout=3000)  # debounced write
    window.workspace.close_key(session.key)
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.emin == -3.0 and session.defaults.emin == -5.0
    window.params.set_param("emax", 2.0)
    session = generate(qtbot, window, folder, auto_export=False)  # regenerate flushes first
    assert (session.params.emin, session.params.emax) == (-3.0, 2.0)


def test_pan_zoom_is_saved(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    generate(qtbot, window, folder, auto_export=False)
    ax = window.current_plot().figure.axes[0]
    ax.set_ylim(-2.0, 1.0)
    ax.set_xlim(0.5, 2.0)
    window.current_plot()._on_release(None)
    window.plot_settings.flush_now()
    stored = yaml.safe_load((folder / "bands.plot").read_text())["params"]
    assert (stored["emin"], stored["emax"], stored["xmin"], stored["xmax"]) == (-2.0, 1.0, 0.5, 2.0)


def test_restore_defaults(qtbot, main_window, demo_project, no_dialogs, monkeypatch):
    window = main_window
    folder = demo_project / "03_bands"
    session = generate(qtbot, window, folder, auto_export=False)
    window.params.set_param("emin", -3.0)
    window.params.set_param("background", "#000000")
    window.plot_settings.flush_now()
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.Yes),
    )
    button = next(
        b for b in window.params.body.findChildren(QPushButton) if b.text() == "Restaurar padrões"
    )
    button.click()
    assert "bands.plot" in asked[0]
    assert session.params == session.defaults and not (folder / "bands.plot").exists()
    figure = window.current_plot().figure
    assert figure.axes[0].get_ylim() == (-5.0, 5.0) and to_hex(figure.get_facecolor()) == "#ffffff"
    window.plot_settings.flush_now()
    assert not (folder / "bands.plot").exists()


def test_invalid_plot_file_is_reported(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    (folder / "bands.plot").write_text("lain_plot: 1\nkind: bands\nparams: [broken")
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params == session.defaults
    assert window.status.message.text() == "bands.plot inválido; usando ajustes padrão."


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_read_only_folder_warns_once(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    generate(qtbot, window, folder, auto_export=False)
    folder.chmod(0o555)
    try:
        window.params.set_param("emin", -3.0)
        window.plot_settings.flush_now()
        message = window.status.message.text()
        assert message.startswith("Não foi possível salvar bands.plot em 03_bands")
        window.status.set_message("")
        window.params.set_param("emin", -2.0)
        window.plot_settings.flush_now()
        assert window.status.message.text() == ""  # once per plot and run
    finally:
        folder.chmod(0o755)
    assert not (folder / "bands.plot").exists()


def test_plot_button_previews_without_saving(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    window.explorer.select_path(folder)
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.activity.plot.click()
    assert blocker.args[0].folder == folder and window.current_plot() is not None
    assert not (folder / "plots").exists()
    assert window.workspace.isVisible() and window.left.currentIndex() == 1
    assert window.activity.plot.isChecked()


def test_plot_button_never_asks_to_overwrite(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    generate(qtbot, window, folder)  # "Gerar Gráfico": plots and saves
    saved = sorted(p.name for p in (folder / "plots").iterdir())
    window.workspace.close_key(window.current_plot().session.key)
    window.set_left_mode("tree")  # plot closed, back to the tree: next Plot click opens
    window.explorer.select_path(folder)
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window.activity.plot.click()
    assert no_dialogs["overwrite"] == []
    assert sorted(p.name for p in (folder / "plots").iterdir()) == saved


def test_plot_button_reuses_the_open_plot(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    generate(qtbot, window, folder, auto_export=False)
    view = window.current_plot()
    window.params.set_param("emin", -3.0)
    window.open_file(folder / "bands.in")
    window.set_left_mode("tree")
    window.explorer.select_path(folder)
    with qtbot.assertNotEmitted(window.plot_ready, wait=200):
        window.activity.plot.click()
    assert window.plot_workflow._detecting == {}
    assert window.current_plot() is view and view.session.params.emin == -3.0
    assert window.params.session is view.session and window.left.currentIndex() == 1


def test_second_plot_click_hides_the_plot(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    plot = window.activity.plot
    window.explorer.select_path(demo_project / "03_bands")
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        plot.click()
    view = window.current_plot()
    assert window.workspace.isVisible() and window.left.currentIndex() == 1 and plot.isChecked()

    plot.click()
    assert not window.workspace.isVisible() and not window.top_bar.toggles["workspace"].isChecked()
    assert window.left.isVisible() and window.left.currentIndex() == 0
    assert not plot.isChecked() and window.activity.tree.isChecked()

    with qtbot.assertNotEmitted(window.plot_ready, wait=200):
        plot.click()  # opens again, reusing the tab
    assert window.workspace.isVisible() and window.left.currentIndex() == 1 and plot.isChecked()
    assert window.current_plot() is view


def test_placeholder_generates_and_saves(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    window.explorer.select_path(folder)
    window.set_left_mode("params")
    button = window.params.body.findChild(QPushButton)
    assert button.text() == "Gerar gráfico"
    with qtbot.waitSignals([window.plot_ready, window.export_finished], timeout=10_000):
        button.click()
    assert (folder / "plots" / "bands.png").exists()


def test_readout_follows_the_plot_on_screen(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    session = generate(qtbot, window, folder, auto_export=False)
    readout = window.status.readout
    text = readout.text()
    assert text.startswith("03_bands · E_F = 8.0584 eV") and "px (300 DPI)" in text

    window.open_file(folder / "bands.in")
    assert readout.text() == ""
    window.workspace.set_current(window.workspace.widget_for(session.key))
    assert readout.text() == text

    window.set_panel_visible("workspace", False)
    assert readout.text() == ""
    window.set_panel_visible("workspace", True)
    assert readout.text() == text

    window.explorer.select_path(demo_project / "04_pdos")
    assert window.files.folder == demo_project / "04_pdos" and readout.text() == text

    window.workspace.close_key(session.key)  # the text tab becomes current
    assert readout.text() == ""
    session = generate(qtbot, window, folder, auto_export=False)
    window.workspace.close_key(str(folder / "bands.in"))
    assert readout.text() == text
    window.workspace.close_key(session.key)  # no tabs left
    assert readout.text() == "" and window.workspace.isVisible()


# -- the parameters panel keeps one body per open plot (spec 8, R5) -----------------------------
def section_of(body, title):
    return next(s for s in body.findChildren(Section) if s.title == title)


def test_generating_a_plot_binds_the_panel_once(
    qtbot, main_window, demo_project, no_dialogs, monkeypatch
):
    window = main_window
    bound = []
    original = window.params.bind
    monkeypatch.setattr(window.params, "bind", lambda s: (bound.append(s), original(s))[1])
    session = generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    assert bound == [session]


def test_switching_plot_tabs_keeps_each_body_and_its_closed_sections(
    qtbot, main_window, demo_project, no_dialogs
):
    window = main_window
    bands = generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    bands_body = window.params.body
    pdos = generate(qtbot, window, demo_project / "04_pdos", auto_export=False)
    pdos_body = window.params.body
    assert pdos_body is not bands_body and window.params.session is pdos

    section = section_of(bands_body, "Estilo")
    assert section.header.isChecked()
    section.header.setChecked(False)
    window.workspace.set_current(window.workspace.widget_for(bands.key))
    assert window.params.body is bands_body and window.params.session is bands
    assert section.body.isHidden() and not section.header.isChecked()
    window.workspace.set_current(window.workspace.widget_for(pdos.key))
    assert window.params.body is pdos_body


def test_section_state_is_remembered_per_kind_across_bodies(
    qtbot, main_window, demo_project, no_dialogs
):
    window = main_window
    first = generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    section_of(window.params.body, "Estilo").header.setChecked(False)
    assert window.settings.value("params/sections/bands/Estilo", type=bool) is False
    window.workspace.close_key(first.key)  # the body dies with its tab
    assert window.params.session is None
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    assert not section_of(window.params.body, "Estilo").header.isChecked()
    assert not section_of(window.params.body, "Arquivos").header.isChecked()  # closed by default
    assert section_of(window.params.body, "Figura").header.isChecked()


def test_regenerating_a_plot_builds_a_new_body(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    body = window.params.body
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    assert window.params.body is not body


def test_a_changed_schema_rebuilds_the_body(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    session = generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    body = window.params.body
    window.params.bind(session)  # same session, same schema: nothing is rebuilt
    assert window.params.body is body
    session.dataset.fermi = None  # fewer energy references → another schema
    window.params.bind(session)
    assert window.params.body is not body


def test_the_dependent_fields_refresh_after_an_edit(qtbot, main_window, demo_project, no_dialogs):
    """``ParamField.refreshes``: changing the reference moves emin/emax in their widgets."""
    window = main_window
    generate(qtbot, window, demo_project / "03_bands", auto_export=False)
    spin = next(
        s
        for s in window.params.body.findChildren(QDoubleSpinBox)
        if s.suffix().strip() == "eV" and s.value() == -5.0
    )
    window.params.set_param("reference", "absolute")
    assert spin.value() == pytest.approx(-5.0 + 8.0584, abs=1e-3)  # 3 decimals


def test_series_rows_are_updated_in_place(qtbot):
    series = SeriesList()
    qtbot.addWidget(series)
    overrides: dict[str, str] = {}
    series.set_series({"Al s": "#111111", "Al p": "#222222"}, [], overrides)
    checks = series.findChildren(QCheckBox)
    assert [c.text() for c in checks] == ["Al s", "Al p"] and all(c.isChecked() for c in checks)

    hidden = ["Al p"]
    with qtbot.assertNotEmitted(series.changed):
        series.set_series({"Al s": "#333333", "Al p": "#222222"}, hidden, overrides)
    assert series.findChildren(QCheckBox) == checks  # same widgets
    assert [c.isChecked() for c in checks] == [True, False]

    checks[0].setChecked(False)  # the user hides a series: it lands in the parameter's list
    assert hidden == ["Al p", "Al s"]
    series.set_series({"Al d": "#444444"}, hidden, overrides)  # other labels: rows rebuilt
    qtbot.waitUntil(lambda: [c.text() for c in series.findChildren(QCheckBox)] == ["Al d"])
