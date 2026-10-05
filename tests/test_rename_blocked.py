"""Renaming is refused while a sync, push, export, derived SCF or new calculation works inside the
path (spec 27-3 R2); with none of them it works as before."""

import threading
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QMessageBox

from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.core.sync.request import Direction, sync_scope
from qe_studio.ui.plot_export import PlotExporter

TARGET = "qe_studio.ui.rename_controller.ask_rename"


@pytest.fixture
def asked(monkeypatch):
    """The paths the rename dialog was opened for; it answers ``<name>-new``."""
    calls = []
    monkeypatch.setattr(TARGET, lambda parent, path: calls.append(path) or f"{path.name}-new")
    return calls


@pytest.fixture
def explained(monkeypatch):
    """What the refusals said (``QMessageBox.information``)."""
    texts = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda parent, title, text: texts.append(text))
    )
    return texts


@pytest.fixture
def sync_running(main_window):
    """``start(folder, push=False)`` makes the window's coordinator look busy with ``folder``."""
    sync = main_window.sync

    def start(folder, push=False):
        direction = Direction.PUSH if push else Direction.PULL
        sync.controller = SimpleNamespace(running=True, shutdown=lambda: None)
        sync.scope = sync_scope(main_window.config, folder, direction=direction)

    yield start
    sync.controller = sync.scope = None


def test_a_sync_of_the_folder_blocks_it_its_parents_and_its_children(
    main_window, demo_project, sync_running, asked, explained
):
    sync_running(demo_project / "03_bands")
    window = main_window
    for path in (
        demo_project / "03_bands",  # the folder itself
        demo_project / "03_bands" / "bands.in",  # inside it
        demo_project,  # above it
    ):
        window.rename_path(path)
    assert asked == [] and len(explained) == 3
    assert explained[0] == (
        "Há uma sincronização em andamento em 03_bands. Espere terminar ou cancele."
    )
    assert (demo_project / "03_bands" / "bands.in").exists()


def test_a_sibling_is_not_blocked(main_window, demo_project, sync_running, asked, explained):
    sync_running(demo_project / "03_bands")
    main_window.rename_path(demo_project / "04_pdos")
    assert asked == [demo_project / "04_pdos"] and explained == []
    assert (demo_project / "04_pdos-new").is_dir()


def test_the_whole_project_blocks_everything(
    main_window, demo_project, sync_running, asked, explained
):
    sync_running(demo_project)
    main_window.rename_path(demo_project / "04_pdos")
    assert asked == [] and explained == [
        "Há uma sincronização em andamento em toda a pasta raiz. Espere terminar ou cancele."
    ]


def test_a_push_says_so(main_window, demo_project, sync_running, asked, explained):
    sync_running(demo_project / "02_scf", push=True)
    main_window.rename_path(demo_project / "02_scf")
    assert explained == [
        "Há um envio ao cluster em andamento em 02_scf. Espere terminar ou cancele."
    ]


def test_an_idle_coordinator_blocks_nothing(main_window, demo_project, asked, explained):
    assert main_window.sync.folder is None
    assert main_window.renamer.blocked(demo_project / "03_bands") is None


def test_an_export_in_progress_blocks_the_rename(
    main_window, demo_project, monkeypatch, asked, explained
):
    monkeypatch.setattr(PlotExporter, "running", property(lambda self: True))
    main_window.rename_path(demo_project / "04_pdos")
    assert asked == [] and explained == [
        "Há uma exportação de figura em andamento. Espere terminar e tente de novo."
    ]
    assert (demo_project / "04_pdos").is_dir()


def test_an_export_that_starts_while_the_dialog_is_open_refuses_it_after_the_dialog(
    qtbot, main_window, demo_project, monkeypatch, explained
):
    """The dialog is modal but the event loop runs: a plot that finishes can start an export."""
    monkeypatch.setattr(TARGET, lambda parent, path: f"{path.name}-new")
    monkeypatch.setattr(main_window.plot_workflow, "wait_for_exports", lambda: False)
    main_window.renamer._wait_for_exports = main_window.plot_workflow.wait_for_exports
    main_window.rename_path(demo_project / "04_pdos")
    assert explained == [
        "Há uma exportação de figura em andamento. Espere terminar e tente de novo."
    ]
    assert (demo_project / "04_pdos").is_dir() and not (demo_project / "04_pdos-new").exists()


def test_a_derived_scf_being_written_blocks_its_folder_then_releases_it(
    qtbot, main_window, demo_project, asked, explained
):
    window = main_window
    output = demo_project / "01_relax" / "relax.out"
    gate = threading.Event()
    window.derive._tasks.submit(f"scf:{output}", gate.wait, 10)

    window.rename_path(demo_project / "01_relax")  # the folder above the output
    window.rename_path(output)  # the output itself
    window.rename_path(demo_project / "02_scf")  # unrelated: goes on
    assert asked == [demo_project / "02_scf"]
    assert (
        explained
        == ["Há um SCF convergido sendo gerado a partir de relax.out. Espere terminar."] * 2
    )

    gate.set()
    qtbot.waitUntil(lambda: window.derive._tasks.active(f"scf:{output}") is None, timeout=5000)
    window.rename_path(demo_project / "01_relax")
    assert asked[-1] == demo_project / "01_relax" and len(explained) == 2
    assert (demo_project / "01_relax-new").is_dir()


def test_a_calculation_being_created_blocks_the_folder_it_is_made_in(
    main_window, demo_project, asked, explained
):
    window = main_window
    window.calc_create._creating = demo_project / "03_bands"
    window.rename_path(demo_project / "03_bands")
    window.rename_path(demo_project)
    window.rename_path(demo_project / "04_pdos")
    assert asked == [demo_project / "04_pdos"]
    assert explained == ["Há um cálculo sendo criado em 03_bands. Espere terminar."] * 2
    window.calc_create._creating = None
    assert window.renamer.blocked(demo_project / "03_bands") is None


def test_a_refusal_changes_nothing(
    qtbot, main_window, demo_project, sync_running, asked, explained
):
    """No ``.plot`` is written, no tab closes, the pending settings stay pending."""
    window = main_window
    folder = demo_project / "03_bands"
    with qtbot.waitSignal(window.plot_ready, timeout=10_000) as blocker:
        window.generate_plot_for(folder, auto_export=False)
    session = blocker.args[0]
    window.params.set_param("emin", -3.0)
    assert window.plot_settings.is_dirty(session.key)

    sync_running(folder)
    window.rename_path(folder)
    assert explained and window.plot_settings.is_dirty(session.key)
    assert read_plot_file(folder, "bands")[0] is None  # nothing written
    assert window.workspace.widget_for(session.key) is not None
    assert folder.is_dir()
