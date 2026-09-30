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
from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton

from qe_studio.core.calculations.base import Method
from qe_studio.ui import main_window as main_window_module
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
    assert to_hex(imread(folder / "plots" / "bands.png")[0, 0]) == "#ffffff"  # dark app theme

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
    window._on_loaded(session.result, session.dataset, (None, []), False)
    new = window.current_plot().session
    assert new is not session and new.params.emin == -3.0 and new.defaults.emin == -5.0


def test_detected_results_survive_an_invalidation(qtbot, main_window, demo_project, no_dialogs):
    """A refresh or sync between detection and the next loop turn must not lose the results."""
    window = main_window
    folder = demo_project / "03_bands"
    window.service.detect_now(folder)
    window._detecting[str(folder)] = False
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
        window._on_detected(str(folder))
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
    assert "Cor de fundo" in labels and "background" in window.params._setters
    figure = window.current_plot().figure
    window.params._set("background", "#123456")
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
    on_gui_thread = []
    real = main_window_module.manual_result

    def manual_result(*args):
        on_gui_thread.append(threading.current_thread() is threading.main_thread())
        return real(*args)

    monkeypatch.setattr(main_window_module, "manual_result", manual_result)
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
    window.params._set("panels", "energy")
    assert [p.name for p in window.export_plot()] == [
        "relax_energia.png",
        "relax_energia.svg",
        "relax_energia.pdf",
    ]
    session.apply_limits((1.0, 4.0), (1e-6, 1e-2))  # toolbar zoom: only the step range
    assert (session.params.xmin, session.params.xmax) == (1.0, 4.0)
    session.reset_view()
    assert (session.params.xmin, session.params.xmax) == (None, None)


def test_scf_folder_asks_for_a_mapping(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    window.generate_plot_for(demo_project / "02_scf")
    qtbot.waitUntil(lambda: bool(no_dialogs["mapping"]), timeout=5000)
    message = no_dialogs["mapping"][0][4]
    assert "SCF" in message and "relaxamento" in message
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


def test_typed_labels_are_saved_in_the_plot_file(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    session = generate(qtbot, window, folder, auto_export=False)
    window.params._set("labels", "W, G, X, K, G")
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
    window.params._set("labels", "")
    window._flush_plot_files()
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.labels == ""


def test_plot_settings_persist(qtbot, main_window, demo_project, no_dialogs):
    window = main_window
    folder = demo_project / "03_bands"
    path = folder / "bands.plot"
    session = generate(qtbot, window, folder, auto_export=False)
    window._flush_plot_files()
    assert not path.exists()  # generating alone never writes
    window.params._set("emin", -3.0)
    qtbot.waitUntil(path.exists, timeout=3000)  # debounced write
    window.workspace.close_key(session.key)
    session = generate(qtbot, window, folder, auto_export=False)
    assert session.params.emin == -3.0 and session.defaults.emin == -5.0
    window.params._set("emax", 2.0)
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
    window._flush_plot_files()
    stored = yaml.safe_load((folder / "bands.plot").read_text())["params"]
    assert (stored["emin"], stored["emax"], stored["xmin"], stored["xmax"]) == (-2.0, 1.0, 0.5, 2.0)


def test_restore_defaults(qtbot, main_window, demo_project, no_dialogs, monkeypatch):
    window = main_window
    folder = demo_project / "03_bands"
    session = generate(qtbot, window, folder, auto_export=False)
    window.params._set("emin", -3.0)
    window.params._set("background", "#000000")
    window._flush_plot_files()
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
    window._flush_plot_files()
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
        window.params._set("emin", -3.0)
        window._flush_plot_files()
        message = window.status.message.text()
        assert message.startswith("Não foi possível salvar bands.plot em 03_bands")
        window.status.set_message("")
        window.params._set("emin", -2.0)
        window._flush_plot_files()
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
    window.params._set("emin", -3.0)
    window.open_file(folder / "bands.in")
    window.set_left_mode("tree")
    window.explorer.select_path(folder)
    with qtbot.assertNotEmitted(window.plot_ready, wait=200):
        window.activity.plot.click()
    assert window._detecting == {}
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
    with qtbot.waitSignal(window.plot_ready, timeout=10_000):
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
