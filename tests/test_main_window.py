from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.config import LoadedConfig, parse_config
from qe_studio.core.sync.controller import SyncReport, SyncStatus
from qe_studio.core.sync.rsync import Endpoint
from qe_studio.ui.layout_controller import fit_widths
from qe_studio.ui.main_window import MainWindow
from qe_studio.ui.widgets.bars import ActivityBar
from qe_studio.ui.widgets.fs_model import SORT_DATE
from qe_studio.ui.widgets.text_viewer import TextViewer
from qe_studio.ui.widgets.workspace import ImageViewer

FIXTURES = Path(__file__).parent / "fixtures"


def wait_detected(qtbot, window, folder: Path):
    if window.service.results(folder) is None:
        with qtbot.waitSignal(window.service.detected, timeout=5000):
            pass
    return window.service.results(folder)


def test_window_builds_with_badges(qtbot, main_window, demo_project):
    window = main_window
    assert window.explorer.root == demo_project
    badges = {
        name: [r.badge for r in window.service.detect_now(demo_project / name)]
        for name in ("01_relax", "02_scf", "03_bands", "04_pdos")
    }
    assert badges == {
        "01_relax": ["RELAX"],
        "02_scf": ["SCF"],
        "03_bands": ["BANDS"],
        "04_pdos": ["PDOS"],
    }
    assert window.top_bar.cluster_label.text() == "cluster não configurado"


def test_hidden_dirs_are_filtered(qtbot, main_window, demo_project):
    window = main_window
    window.explorer.select_path(demo_project / "03_bands")
    model = window.files.model
    with qtbot.waitSignal(model.directoryLoaded, timeout=5000):
        window.files.set_folder(demo_project / "03_bands")
    root = window.files.view.rootIndex()
    names = {
        window.files.proxy.path(window.files.proxy.index(r, 0, root)).name
        for r in range(window.files.proxy.rowCount(root))
    }
    assert "bands.in" in names and "tmp" not in names


def visible_names(panel) -> set[str]:
    root = panel.view.rootIndex()
    return {
        panel.proxy.path(panel.proxy.index(r, 0, root)).name
        for r in range(panel.proxy.rowCount(root))
    }


def test_reload_config_replaces_monitor_and_filters(qtbot, main_window, demo_project, monkeypatch):
    window = main_window
    model = window.files.model
    with qtbot.waitSignal(model.directoryLoaded, timeout=5000):
        window.files.set_folder(demo_project / "04_pdos")
    assert "orbitals" in visible_names(window.files)
    config = parse_config(
        {"paths": {"local_root": str(demo_project)}, "ui": {"hidden_dirs": ["tmp", "orbitals/"]}}
    )
    monkeypatch.setattr(
        "qe_studio.ui.main_window.load_config", lambda _path: LoadedConfig(config, None)
    )
    old = window.monitor
    window.reload_config()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert window.monitor is not old and sip.isdeleted(old)
    with qtbot.waitSignal(model.directoryLoaded, timeout=5000, raising=False):
        window.files.set_folder(demo_project / "04_pdos")
    assert "orbitals" not in visible_names(window.files)
    assert window.explorer.proxy.hidden_dirs == ["tmp", "orbitals"]


def test_folder_counts_load_off_the_gui_thread(qtbot, main_window, demo_project):
    panel = main_window.files
    folder = demo_project / "04_pdos"
    expected = sum(1 for p in folder.iterdir() if not p.name.startswith("."))
    panel.refresh()
    qtbot.waitUntil(lambda: panel.item_count(folder) is not None, timeout=5000)
    assert panel.item_count(folder) == expected


def test_folder_selection_updates_panels(qtbot, main_window, demo_project):
    window = main_window
    window.on_folder_selected(demo_project / "04_pdos")
    assert window.files.folder == demo_project / "04_pdos"
    assert window.top_bar.breadcrumb.toolTip() == str(demo_project / "04_pdos")
    assert window.status.path.text() == "04_pdos"


def test_open_text_and_image(qtbot, main_window, demo_project, tmp_path):
    window = main_window
    path = demo_project / "03_bands" / "bands.in"
    window.open_file(path)
    viewer = window.workspace.widget_for(str(path))
    assert isinstance(viewer, TextViewer)
    if not viewer.editor.toPlainText():
        with qtbot.waitSignal(viewer.loaded, timeout=5000):
            pass
    assert "K_POINTS {crystal_b}" in viewer.editor.toPlainText()
    window.open_file(path)  # reuses the tab
    assert window.workspace.tabs.count() == 1

    from PyQt6.QtGui import QColor, QImage

    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    png = tmp_path / "fig.png"
    image.save(str(png))
    window.open_file(png)
    assert isinstance(window.workspace.current(), ImageViewer)
    assert window.workspace.current().natural_size.width() == 40
    window.workspace.close_tab(0)
    window.workspace.close_tab(0)
    assert window.workspace.current() is None


def open_text(qtbot, window, path: Path) -> TextViewer:
    window.open_file(path)
    viewer = window.workspace.widget_for(str(path))
    assert isinstance(viewer, TextViewer)
    # The worker's result reaches the viewer through a queued connection: not delivered yet.
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    return viewer


def test_job_logs_open_with_a_state_banner(qtbot, main_window, tmp_path):
    window = main_window
    empty = tmp_path / "job.o1"
    empty.write_text("")
    viewer = open_text(qtbot, window, empty)
    assert not viewer.banner.isHidden() and viewer.banner.property("level") == "success"
    assert viewer.banner.text() == "Arquivo vazio: o job não registrou erros."
    assert not window.workspace.isHidden()

    failed = tmp_path / "job.e2"
    failed.write_text("forrtl: severe (174): SIGSEGV, segmentation fault occurred\n")
    viewer = open_text(qtbot, window, failed)
    assert viewer.banner.property("level") == "error"
    assert viewer.banner.text() == "O job registrou mensagens de erro."
    assert "SIGSEGV" in viewer.editor.toPlainText()

    # pw.x without output redirection writes into the queue log: no job verdict.
    redirected = tmp_path / "run.o3"
    redirected.write_bytes((FIXTURES / "si_relax" / "si.rel.out").read_bytes())
    viewer = open_text(qtbot, window, redirected)
    assert "JOB DONE" in viewer.editor.toPlainText() and viewer.banner.isHidden()


def test_job_log_label_in_grid(main_window, tmp_path):
    delegate = main_window.files.view.itemDelegate()
    assert delegate._meta(tmp_path / "job.o1", False, 0) == ("SEM ERROS", "success")
    assert delegate._meta(tmp_path / "job.o1", False, 2048) == ("ERRO", "error")
    main_window.files.set_grid_mode(False)  # list mode keeps the size (spec 5 R1.3)
    assert delegate._meta(tmp_path / "job.o1", False, 0) == ("0 B · SEM ERROS", "success")
    assert delegate._meta(tmp_path / "job.o1", False, 2048) == ("2.0 KB · ERRO", "error")
    assert delegate._meta(tmp_path / "notes.txt", False, 10) == ("10 B", "text_dim")


@pytest.mark.parametrize("name", ["job.qsub", "job.slurm", "job.pbs", "run.sh"])
def test_submission_scripts_are_read_only(qtbot, main_window, tmp_path, name):
    script = tmp_path / name
    script.write_text("#!/bin/bash\n#PBS -N si\nmpirun pw.x -in scf.in > scf.out\n")
    viewer = open_text(qtbot, main_window, script)
    assert viewer.editor.isReadOnly() and "mpirun" in viewer.editor.toPlainText()


def test_theme_toggle_persists(qtbot, main_window):
    window = main_window
    window.toggle_theme()
    assert window.theme.name == "light"
    assert window.settings.value("ui/theme") == "light"
    window.toggle_theme()
    assert window.theme.name == "dark"


def test_panel_toggles(qtbot, main_window):
    window = main_window
    window.set_panel_visible("grid", False)
    assert not window.files.isVisible()
    assert not window.activity.grid.isChecked() and not window.top_bar.toggles["grid"].isChecked()
    window.activity.grid.click()
    assert window.files.isVisible()
    window.set_left_mode("params")
    assert window.left.currentIndex() == 1
    assert window.activity.plot.isChecked() and not window.activity.tree.isChecked()
    window.set_left_mode("tree")
    assert window.left.currentIndex() == 0
    assert window.activity.tree.isChecked() and not window.activity.plot.isChecked()


def test_activity_bar_has_no_params_button(qtbot, main_window):
    assert not hasattr(main_window.activity, "params")
    assert not hasattr(ActivityBar, "params_requested")


def test_workspace_starts_hidden(qtbot, main_window):
    window = main_window
    assert not window.workspace.isVisible()
    assert not window.top_bar.toggles["workspace"].isChecked()
    tree, grid, workspace = window.splitter.sizes()
    assert workspace == 0
    assert tree + grid == window.splitter.width() - window.splitter.handleWidth()
    assert tree == pytest.approx((tree + grid) * 280 / 600, abs=2)


def test_viewable_files_open_the_workspace(qtbot, main_window, demo_project, tmp_path, monkeypatch):
    window = main_window
    window.open_file(demo_project / "03_bands" / "bands.in")
    assert window.workspace.isVisible() and window.top_bar.toggles["workspace"].isChecked()

    from PyQt6.QtGui import QColor, QImage

    window.set_panel_visible("workspace", False)
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    png = tmp_path / "fig.png"
    image.save(str(png))
    window.open_file(png)
    assert window.workspace.isVisible()

    window.set_panel_visible("workspace", False)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(opened.append))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    window.open_file(pdf)
    assert len(opened) == 1 and not window.workspace.isVisible()

    scf = demo_project / "02_scf" / "scf.out"
    window.explorer.tree.activated.emit(window.explorer.proxy.index_for(scf))  # Enter
    assert window.workspace.isVisible() and window.workspace.widget_for(str(scf)) is not None


def test_fit_widths():
    minimums = {"tree": 200, "grid": 170, "workspace": 320}
    assert fit_widths({"tree": 280, "grid": 320}, minimums, 1440) == {"tree": 672, "grid": 768}
    widths = {"tree": 672, "grid": 768, "workspace": 840}
    reopened = fit_widths(widths, minimums, 1440, keep="workspace")
    assert reopened == {"workspace": 840, "tree": 280, "grid": 320}
    # Not enough room: the restored width shrinks and nobody goes below its minimum.
    tight = fit_widths(widths, minimums, 700, keep="workspace")
    assert tight == {"workspace": 330, "tree": 200, "grid": 170}
    assert fit_widths({"tree": 100, "grid": 900}, minimums, 1000) == {"tree": 200, "grid": 800}


def test_hiding_the_workspace_keeps_the_ratio(qtbot, main_window):
    window = main_window
    splitter = window.splitter
    window.set_panel_visible("workspace", True)
    total = sum(splitter.sizes())
    splitter.setSizes([280, 320, total - 600])
    before = splitter.sizes()
    assert before == [280, 320, total - 600]
    window.set_panel_visible("workspace", False)
    tree, grid, workspace = splitter.sizes()
    assert workspace == 0 and tree + grid == total + splitter.handleWidth()
    assert tree == pytest.approx((tree + grid) * 280 / 600, abs=2)
    window.top_bar.toggles["workspace"].click()
    assert splitter.sizes() == before


def test_hiding_the_grid_keeps_the_ratio(qtbot, main_window):
    window = main_window
    splitter = window.splitter
    window.set_panel_visible("workspace", True)
    total = sum(splitter.sizes())
    splitter.setSizes([300, 300, total - 600])
    before = splitter.sizes()
    window.activity.grid.click()
    tree, grid, workspace = splitter.sizes()
    assert grid == 0 and tree + workspace == total + splitter.handleWidth()
    assert tree == pytest.approx((tree + workspace) * 300 / (total - 300), abs=2)
    window.activity.grid.click()
    assert splitter.sizes() == before


def test_dragged_divider_is_remembered(qtbot, main_window):
    window = main_window
    splitter = window.splitter
    window.set_panel_visible("workspace", True)
    total = sum(splitter.sizes())
    splitter.setSizes([250, 250, total - 500])
    splitter.splitterMoved.emit(250, 1)
    window.set_panel_visible("workspace", False)
    window.set_panel_visible("workspace", True)
    assert splitter.sizes() == [250, 250, total - 500]


def test_close_saves_state(qtbot, main_window):
    window = main_window
    window.close()
    widths = [int(w) for w in window.settings.value("layout/panel_widths")]
    assert len(widths) == 3 and min(widths) > 0
    assert widths[2] == 840  # never shown, but its width is kept
    assert window.settings.value("layout/grid_visible", type=bool)


def reopen(qtbot, window):
    """A new MainWindow on the same settings file, like the next run of the app."""
    window.close()
    settings = QSettings(window.settings.fileName(), QSettings.Format.IniFormat)
    new = MainWindow(window.loaded, window.theme, settings, window.memory)
    qtbot.addWidget(new)
    new.show()
    return new


def test_layout_and_navigation_survive_a_restart(qtbot, main_window, demo_project):
    window = main_window
    window.set_panel_visible("workspace", True)
    total = sum(window.splitter.sizes())
    window.splitter.setSizes([300, 250, total - 550])
    window.set_panel_visible("grid", False)
    window.files.set_grid_mode(False)
    window.files.set_sort(SORT_DATE)
    window.explorer.select_path(demo_project / "04_pdos")

    new = reopen(qtbot, window)
    assert new.workspace.isHidden() and new.files.isHidden() and not new.left.isHidden()
    assert not new.files.grid_mode and new.files.sort_column == SORT_DATE
    assert new.files._sort_actions[SORT_DATE].isChecked()
    assert new.files.folder == demo_project / "04_pdos"
    assert new.current_folder() == demo_project / "04_pdos"
    assert (
        new.panel_layout.panel_widths["tree"] == 300
        and new.panel_layout.panel_widths["grid"] == 250
    )
    # Restored geometry is clamped to the screen (800 px wide when offscreen), and panels shrink
    # to fit a narrower window, so lay the sizes out in a window as wide as the one they came from.
    new.resize(1440, 900)
    new.set_panel_visible("grid", True)
    new.set_panel_visible("workspace", True)
    tree, grid, workspace = new.splitter.sizes()
    assert tree == pytest.approx(300, abs=2) and grid == pytest.approx(250, abs=2)
    new.close()


def test_old_splitter_key_is_migrated(qtbot, main_window):
    window = main_window
    window.settings.setValue("window/splitter", [300, 300, 0])
    window.settings.setValue("window/grid_visible", False)
    window.panel_layout.restore()
    assert window.panel_layout.panel_widths["workspace"] == 840  # the zero was ignored
    assert window.files.isHidden()
    assert window.settings.value("window/splitter") is None
    assert window.settings.value("window/grid_visible") is None
    window.settings.setValue("window/splitter", [310, 290, 700])
    window.panel_layout.restore()
    assert window.panel_layout.panel_widths == {"tree": 310, "grid": 290, "workspace": 700}


@pytest.mark.parametrize("last", ["missing", "outside"])
def test_unusable_last_folder_falls_back_to_the_root(qtbot, main_window, demo_project, last):
    window = main_window
    folder = demo_project / "gone" if last == "missing" else demo_project.parent
    window.settings.setValue("explorer/last_folder", str(folder))
    window._restore_folder()
    assert window.files.folder == demo_project


def test_sync_keeps_detection_outside_the_synced_folder(
    qtbot, main_window, demo_project, monkeypatch
):
    window = main_window
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    relax, bands = demo_project / "01_relax", demo_project / "03_bands"
    for folder in (relax, bands):
        window.service.detect_now(folder)
    synced = bands / "tmp"
    window.sync._on_finished(SyncReport(SyncStatus.DONE, synced, Endpoint("/r/03_bands/tmp")))
    assert window.service.results(relax) is not None
    assert window.service.results(bands) is not None
    assert window.service.file_sniff(bands / "scf.out") is not None
