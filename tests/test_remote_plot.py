"""Plotting in the cluster mode (spec 66 R4): "Plot", "Gerar" and the menu's "Plotar" copy the remote
folder into its mirror's ``tmp_remote/`` and plot the copy, which saves into ``plots_remote/``. The
listing is the fake of spec 65 (``remote_helpers``); the copy is the real rsync from a local folder
standing for the cluster (``serve_locally``). The root holds the demo project, so its folders are
calculations (a first-level folder is a project, never copied)."""

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QItemSelectionModel, QPoint
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.sync.request import SYNC_RUNNING
from qe_studio.ui.remote_controller import PICK
from qe_studio.ui.sync_coordinator import WAIT_RUNNING
from qe_studio.ui.widgets.remote_model import RemotePath

from conftest import copy_fixture
from remote_helpers import REMOTE, FakeListing, entries, menu_spy, remote_window, serve_locally
from remote_helpers import turn_on as turn_on_at

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")

PROJECT = f"{REMOTE}/project"
BANDS = f"{PROJECT}/03_bands"


@pytest.fixture
def cluster(tmp_path_factory, al_pdos_orbitals) -> Path:
    """The "cluster": a bands folder (``al_bands`` as QE wrote it) and a PDOS one (``pdos.qsub``'s
    layout), under the names the demo project has locally."""
    root = tmp_path_factory.mktemp("cluster")
    project = root / "project"
    project.mkdir()
    copy_fixture("al_bands", project).rename(project / "03_bands")
    shutil.move(al_pdos_orbitals, project / "04_pdos")
    return root


@pytest.fixture
def boxes(monkeypatch):
    shown = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, kind, staticmethod(lambda *a, k=kind, **kw: shown.append((k, a[2])))
        )
    return shown


@pytest.fixture
def window(window_factory, demo_project, monkeypatch, cluster, boxes):
    fake = FakeListing(
        {
            REMOTE: entries("project"),
            PROJECT: entries("01_relax", "02_scf", "03_bands", "04_pdos", files=("notes.txt",)),
            BANDS: entries(files=("bands.out", "al.scf.out")),
        }
    )
    serve_locally(monkeypatch, cluster)
    return remote_window(window_factory, demo_project.parent, monkeypatch, fake)


def turn_on(qtbot, window, folder: str = PROJECT) -> None:
    """The mode on, showing ``folder``."""
    turn_on_at(qtbot, window, REMOTE)
    with qtbot.waitSignal(window.remote.listed, timeout=5000):
        window.remote.open(folder)
    assert window.remote.current == folder


def select(window, *names: str) -> None:
    """Select the rows named ``names`` in the cluster's list (nothing else)."""
    panel = window.remote.file_panel
    selection = panel.view.selectionModel()
    assert selection is not None
    selection.clearSelection()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for row in range(panel.model.rowCount()):
        index = panel.model.index(row, 0)
        if index.data() in names:
            selection.select(index, flags)
    assert [Path(item.path).name for item in panel.selected_paths()] == list(names)


def mirror_files(folder: Path) -> dict[str, bytes]:
    """The mirror's own files (``tmp_remote/`` left out)."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "tmp_remote" not in p.relative_to(folder).parts
    }


def plot(qtbot, window, generate: bool):
    """The sidebar's "Plot" or the panel's "Gerar": the session and what was saved."""
    with (  # ready is waited for first: the export is asked once the tab is shown
        qtbot.waitSignal(window.export_finished, timeout=30_000) as done,
        qtbot.waitSignal(window.plot_ready, timeout=30_000) as ready,
    ):
        if generate:
            window.generate_plot()
        else:
            window.plot_button()
    return ready.args[0], done.args[0]


def test_plot_opens_the_copy_of_the_remote_folder(qtbot, window, demo_project, boxes):
    mirror = demo_project / "03_bands"
    before = mirror_files(mirror)
    turn_on(qtbot, window)
    select(window, "03_bands")
    session, written = plot(qtbot, window, generate=False)  # never plotted: plotted and saved
    copy = mirror / "tmp_remote"
    assert session.kind == "bands" and session.folder == copy
    assert (copy / "al.band.out").is_file()  # the cluster's own names: it is the copy
    assert written and all(path.parent == copy / "plots_remote" for path in written)
    assert mirror_files(mirror) == before  # nothing of the mirror itself, no plots/ there
    assert boxes == []
    assert window.remote.active  # the mode goes on
    assert window.left.currentWidget() is window.params
    window.activity.tree.click()
    assert window.left.currentWidget() is window.remote.tree_panel  # back to the cluster's tree


def test_gerar_saves_into_plots_remote(qtbot, window, demo_project):
    mirror = demo_project / "03_bands"
    turn_on(qtbot, window, BANDS)  # the folder shown, nothing selected
    session, written = plot(qtbot, window, generate=True)
    remote_plots = mirror / "tmp_remote" / "plots_remote"
    assert session.folder == mirror / "tmp_remote"
    assert remote_plots / "project-03_bands-tmp_remote-bands.png" in written
    assert not (mirror / "plots").exists()

    window.params.set_param("emin", -3.0)  # an edit: the settings are kept next to the figures
    window.plot_settings.flush_now()
    assert (remote_plots / "bands.plot").is_file()


def test_two_folders_make_the_bands_and_dos_figure(qtbot, window, demo_project):
    turn_on(qtbot, window)
    select(window, "03_bands", "04_pdos")
    session, written = plot(qtbot, window, generate=True)
    bands, pdos = demo_project / "03_bands" / "tmp_remote", demo_project / "04_pdos" / "tmp_remote"
    assert session.kind == "bands_dos" and session.paths == (bands, pdos)
    assert bands / "plots_remote" / "project-03_bands-tmp_remote-bands_dos.png" in written
    assert (pdos / "orbitals").is_dir()  # the whole folder was copied
    assert not (pdos / "plots_remote").exists()


def test_a_file_or_three_folders_say_what_to_select(qtbot, window, monkeypatch):
    turn_on(qtbot, window)
    started = []
    monkeypatch.setattr(window.sync, "start_scratch", lambda *a: started.append(a))
    select(window, "notes.txt")
    window.plot_button()
    assert window.status.message.text() == PICK
    select(window, "01_relax", "02_scf", "03_bands")
    window.generate_plot()
    assert window.status.message.text() == PICK == "Selecione uma ou duas pastas para plotar."
    assert started == []


def test_plot_waits_for_a_running_sync(qtbot, window, monkeypatch):
    turn_on(qtbot, window)
    monkeypatch.setattr(type(window.sync), "running", property(lambda self: True))
    select(window, "03_bands")
    window.plot_button()
    assert window.status.message.text() == WAIT_RUNNING
    assert window.sync.dialog is None


def test_the_menu_plots_folders(qtbot, window, monkeypatch, demo_project):
    turn_on(qtbot, window)
    menus = menu_spy(monkeypatch)
    window.remote.show_menu([RemotePath(f"{BANDS}/bands.out", False)], QPoint())
    folders = [RemotePath(f"{PROJECT}/{name}", True) for name in ("01_relax", "02_scf", "03_bands")]
    window.remote.show_menu(folders, QPoint())
    assert [text for text, _on, _tip in menus[0]] == ["Baixar", "Copiar caminho"]  # a file
    assert menus[1][1] == ("Plotar", False, PICK)
    with monkeypatch.context() as busy:
        busy.setattr(type(window.sync), "running", property(lambda self: True))
        window.remote.show_menu([RemotePath(BANDS, True)], QPoint())
    assert menus[2][1] == ("Plotar", False, SYNC_RUNNING)

    menu_spy(monkeypatch, choose="Plotar")
    with qtbot.waitSignal(window.plot_ready, timeout=30_000) as ready:
        window.remote.show_menu([RemotePath(BANDS, True)], QPoint())
    assert ready.args[0].folder == demo_project / "03_bands" / "tmp_remote"


def test_with_the_mode_off_plot_and_gerar_are_local(qtbot, window, monkeypatch, demo_project):
    clicks = []
    workflow = window.plot_workflow
    monkeypatch.setattr(workflow.button, "click", lambda *a: clicks.append(("plot", *a)))
    monkeypatch.setattr(workflow.generator, "click", lambda *a: clicks.append(("gerar", *a)))
    assert window.remote.plot(generate=True) is False
    window.explorer.select_path(demo_project / "03_bands")
    window.plot_button()
    window.generate_plot()
    assert [click[:2] for click in clicks] == [
        ("plot", demo_project / "03_bands"),
        ("gerar", demo_project / "03_bands"),
    ]
    assert not (demo_project / "03_bands" / "tmp_remote").exists()
