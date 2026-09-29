from pathlib import Path

from qe_studio.ui.widgets.workspace import ImageViewer, TextViewer, read_for_viewer


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


def test_folder_selection_updates_panels(qtbot, main_window, demo_project):
    window = main_window
    window.on_folder_selected(demo_project / "04_pdos")
    assert window.files.folder == demo_project / "04_pdos"
    assert window.top_bar.path_chip.toolTip() == str(demo_project / "04_pdos")
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


def test_large_file_shows_head_and_tail(tmp_path):
    big = tmp_path / "big.out"
    big.write_bytes(b"HEAD\n" + b"x" * (5 * 1024 * 1024) + b"\nTAIL JOB DONE.\n")
    text, banner = read_for_viewer(big)
    assert text.startswith("HEAD") and text.rstrip().endswith("JOB DONE.")
    assert "trecho omitido" in text and "Arquivo grande" in banner


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
    assert window.left.currentIndex() == 1 and window.activity.params.isChecked()
    window.set_left_mode("tree")
    assert window.left.currentIndex() == 0


def test_close_saves_state(qtbot, main_window):
    window = main_window
    window.close()
    assert window.settings.value("window/splitter") is not None
