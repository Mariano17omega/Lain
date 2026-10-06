"""``PlotWorkflow`` and ``PlotSettingsStore`` without the main window (spec 15 R4.7): real
workspace, parameters panel and status bar, and the detection service."""

import threading

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMessageBox, QWidget

from qe_studio.core.calculations import module_for
from qe_studio.core.config import parse_config
from qe_studio.core.detection import ManualTarget
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.plotting.plot_file import read_plot_file
from qe_studio.ui import plot_settings, plot_workflow
from qe_studio.ui.plot_settings import PlotSettingsStore
from qe_studio.ui.plot_workflow import PlotWorkflow
from qe_studio.ui.services import DetectionService
from qe_studio.ui.theme.manager import ThemeManager
from qe_studio.ui.widgets.bars import StatusBar
from qe_studio.ui.widgets.plot_params import ParamsPanel
from qe_studio.ui.widgets.plot_view import PlotView
from qe_studio.ui.widgets.workspace import Workspace


class Rig:
    """The workflow with what the window would give it, and what it asks the window."""

    def __init__(self, qtbot, demo_project, tmp_path):
        theme = ThemeManager("dark")
        self.parent = QWidget()
        qtbot.addWidget(self.parent)
        self.config = parse_config({"paths": {"local_root": str(demo_project)}})
        self.memory = FolderMemory(tmp_path / "memory.json")
        self.service = DetectionService(self.memory, self.parent)
        self.workspace = Workspace(theme, self.parent)
        settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        self.params = ParamsPanel(theme, settings=settings, parent=self.parent)
        self.status = StatusBar(theme, self.parent)
        self.settings = PlotSettingsStore(self.parent)
        self.workflow = PlotWorkflow(
            service=self.service,
            workspace=self.workspace,
            params=self.params,
            memory=self.memory,
            settings=self.settings,
            status=self.status,
            theme=theme,
            config=lambda: self.config,
            dialog_parent=self.parent,
            parent=self.parent,
        )
        self.panels, self.messages = [], []
        self.workflow.panel_requested.connect(self.panels.append)
        self.workflow.message.connect(lambda text, level, _ms: self.messages.append((text, level)))
        self.parent.show()

    def generate(self, qtbot, folder, auto_export=False):
        with qtbot.waitSignal(self.workflow.plot_ready, timeout=10_000) as blocker:
            self.workflow.generate(folder, auto_export=auto_export)
        return blocker.args[0]

    def close(self):
        self.workflow.shutdown()
        self.settings.flush_now()
        self.settings.shutdown()
        self.service.shutdown()


@pytest.fixture
def rig(qtbot, demo_project, tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("a dialog was opened")

    monkeypatch.setattr("qe_studio.ui.plot_workflow.ask_mapping", blocked)
    monkeypatch.setattr("qe_studio.ui.plot_export.ask_overwrite", blocked)
    rig = Rig(qtbot, demo_project, tmp_path)
    yield rig
    rig.close()


def test_generate_opens_a_tab_and_asks_for_the_panels(qtbot, rig, demo_project):
    session = rig.generate(qtbot, demo_project / "03_bands")
    view = rig.workspace.current()
    assert isinstance(view, PlotView) and view.session is session
    assert rig.workflow.current_plot() is view and rig.params.session is session
    assert rig.panels == ["workspace", "params"]
    assert ("Estrutura de bandas: 03_bands", "info") in rig.messages
    assert rig.status.readout.full_text().startswith("03_bands · E_F = 8.0584 eV")
    assert rig.status.spinner.isHidden() and rig.workflow.busy.labels == []


def test_preview_brings_an_open_plot_to_front(qtbot, rig, demo_project):
    session = rig.generate(qtbot, demo_project / "03_bands")
    rig.generate(qtbot, demo_project / "04_pdos")
    with qtbot.assertNotEmitted(rig.workflow.plot_ready, wait=100):
        rig.workflow.preview(demo_project / "03_bands")
    assert rig.workflow.current_plot().session is session


def test_export_writes_in_a_worker_and_reports(qtbot, rig, demo_project):
    folder = demo_project / "03_bands"
    rig.generate(qtbot, folder)
    with qtbot.waitSignal(rig.workflow.export_finished, timeout=10_000) as blocker:
        assert rig.workflow.export()
        assert rig.workflow.busy.labels == ["Exportando…"]
    names = ["03_bands-bands.png", "03_bands-bands.svg", "03_bands-bands.pdf", "03_bands-bands.csv"]
    assert [p.name for p in blocker.args[0]] == names
    assert (f"Salvo em plots/: {', '.join(names)}", "info") in rig.messages
    assert rig.workflow.busy.labels == []


def test_export_without_a_plot_or_a_format_explains(qtbot, rig, demo_project):
    assert rig.workflow.export() is False
    assert rig.messages[-1] == ("Nenhum gráfico aberto.", "warning")
    rig.generate(qtbot, demo_project / "03_bands")
    for name in ("export_png", "export_svg", "export_pdf"):
        rig.params.set_param(name, False)
    assert rig.workflow.export() is False
    assert rig.messages[-1] == ("Selecione ao menos um formato de exportação.", "warning")


def test_a_load_failure_is_reported(qtbot, rig, demo_project, monkeypatch):
    import shutil

    from conftest import FIXTURES

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a[2])))
    folder = demo_project / "05_si"
    folder.mkdir()
    for name in ("si.scf.out", "si.band.in", "si.band.out"):
        shutil.copy(FIXTURES / "si_bands" / name, folder / name)
    with qtbot.waitSignal(rig.workflow.plot_failed, timeout=10_000) as blocker:
        rig.workflow.generate(folder)
    assert "bands.x" in blocker.args[0] and warnings == [blocker.args[0]]
    assert ("Falha ao carregar os dados do gráfico.", "error") in rig.messages
    assert rig.workflow.busy.labels == [] and rig.workflow.current_plot() is None


def test_edits_are_written_in_order_before_the_next_read(qtbot, rig, demo_project):
    folder = demo_project / "03_bands"
    session = rig.generate(qtbot, folder)
    rig.params.set_param("emin", -3.0)
    assert rig.settings.is_dirty(session.key)
    rig.workspace.close_key(session.key)  # its write is queued in the settings worker…
    again = rig.generate(qtbot, folder)  # …ahead of this plot's read of bands.plot
    assert again.params.emin == -3.0 and again.defaults.emin == -5.0


def test_settings_writes_warn_once_per_plot(qtbot, rig, demo_project, monkeypatch):
    session = rig.generate(qtbot, demo_project / "03_bands")

    def refuse(*args):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("qe_studio.ui.plot_settings.write_plot_file", refuse)
    warnings = []
    rig.settings.warning.connect(warnings.append)
    for value in (-3.0, -2.0):
        rig.params.set_param("emin", value)
        rig.settings.flush_now()
    assert warnings == ["Não foi possível salvar bands.plot em 03_bands: Permission denied"]
    assert read_plot_file(session.folder, "bands") == (None, [])


def test_restore_defaults_removes_the_file_after_queued_writes(
    qtbot, rig, demo_project, monkeypatch
):
    folder = demo_project / "03_bands"
    session = rig.generate(qtbot, folder)
    rig.params.set_param("emin", -3.0)
    rig.settings.flush()  # queued…
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    rig.workflow.restore_defaults()  # …and the removal after it
    rig.settings.flush_now()
    assert not (folder / "bands.plot").exists() and session.params == session.defaults


# -- a repeated request for a plot that is loading replaces it (spec 27-9 R2) ----------------------
class GatedLoad:
    """``load_plot`` whose calls wait for their gate (by call index); keeps what each one saw."""

    def __init__(self, gated=()):
        self.real = plot_workflow.load_plot
        self.gates = {index: threading.Event() for index in gated}
        self.targets, self.results = [], {}
        self._lock = threading.Lock()

    def __call__(self, target, sniff):
        with self._lock:
            index = len(self.targets)
            self.targets.append(target)
        gate = self.gates.get(index)
        if gate is not None:
            assert gate.wait(10)
        self.results[index] = self.real(target, sniff)
        return self.results[index]


def mappings(session):
    """A full mapping of the open bands plot and a smaller one that still loads."""
    full = {role: list(paths) for role, paths in session.result.files.items()}
    return full, {role: full[role] for role in ("scf_out", "gnu")}


def manual(rig, folder, mapping):
    return ManualTarget(module_for("bands"), folder, mapping, rig.service.sniff_cache.sniff)


def test_a_remap_during_a_load_replaces_it(qtbot, rig, demo_project, monkeypatch):
    opened = rig.generate(qtbot, demo_project / "03_bands")
    first, second = mappings(opened)
    fake = GatedLoad(gated=[0])
    monkeypatch.setattr("qe_studio.ui.plot_workflow.load_plot", fake)
    answers = iter([("bands", first, False), ("bands", second, False)])
    monkeypatch.setattr("qe_studio.ui.plot_workflow.ask_mapping", lambda *a: next(answers))
    shown = []
    rig.workflow.plot_ready.connect(shown.append)
    rig.workflow.remap()
    qtbot.waitUntil(lambda: len(fake.targets) == 1)
    assert rig.workflow.busy.labels == ["Carregando estrutura de bandas…"]
    rig.workflow.remap()  # the plot loads already: this one replaces the first
    assert rig.workflow.busy.labels == ["Carregando estrutura de bandas…"]  # once, not twice
    qtbot.waitUntil(lambda: len(shown) == 1, timeout=10_000)
    fake.gates[0].set()
    qtbot.waitUntil(lambda: 0 in fake.results)  # the first load ends…
    qtbot.wait(200)  # …and its result goes nowhere
    assert len(shown) == 1 and fake.targets[1].mapping == second
    assert shown[0].result is fake.results[1][0]
    assert rig.workspace.current().session is shown[0]
    assert rig.workflow.busy.labels == [] and rig.status.spinner.isHidden()


@pytest.mark.parametrize(
    ("first", "second", "exports"), [(True, False, 1), (False, True, 1), (False, False, 0)]
)
def test_an_export_asked_by_either_request_is_kept(
    qtbot, rig, demo_project, monkeypatch, first, second, exports
):
    folder = demo_project / "03_bands"
    full, _small = mappings(rig.generate(qtbot, folder))
    fake = GatedLoad(gated=[0])
    monkeypatch.setattr("qe_studio.ui.plot_workflow.load_plot", fake)
    shown, written = [], []
    rig.workflow.plot_ready.connect(shown.append)
    rig.workflow.export_finished.connect(written.append)
    rig.workflow._load(manual(rig, folder, full), auto_export=first)
    qtbot.waitUntil(lambda: len(fake.targets) == 1)
    rig.workflow._load(manual(rig, folder, full), auto_export=second)
    qtbot.waitUntil(lambda: len(shown) == 1, timeout=10_000)
    fake.gates[0].set()
    qtbot.wait(300)
    if exports:
        qtbot.waitUntil(lambda: len(written) == exports, timeout=10_000)
    assert len(written) == exports and len(shown) == 1


def test_a_request_while_the_plot_file_is_read_still_shows_the_newest(
    qtbot, rig, demo_project, monkeypatch
):
    folder = demo_project / "03_bands"
    full, small = mappings(rig.generate(qtbot, folder))
    fake = GatedLoad(gated=[1])  # the second load is the slow one
    monkeypatch.setattr("qe_studio.ui.plot_workflow.load_plot", fake)
    real_read, hold, reads = plot_settings.read_plot_file, threading.Event(), []

    def slow_read(*args):
        reads.append(args)
        if len(reads) == 1:
            assert hold.wait(10)
        return real_read(*args)

    monkeypatch.setattr("qe_studio.ui.plot_settings.read_plot_file", slow_read)
    shown = []
    rig.workflow.plot_ready.connect(shown.append)
    rig.workflow._load(manual(rig, folder, full), auto_export=False)
    qtbot.waitUntil(lambda: len(reads) == 1)  # the first load is over, its .plot read waits
    rig.workflow._load(manual(rig, folder, small), auto_export=False)
    qtbot.waitUntil(lambda: len(fake.targets) == 2)
    hold.set()  # the first read ends while the second load is still going: nobody is told
    qtbot.wait(300)
    assert shown == [] and rig.workflow.busy.labels == ["Carregando estrutura de bandas…"]
    fake.gates[1].set()
    qtbot.waitUntil(lambda: len(shown) == 1, timeout=10_000)
    assert shown[0].result is fake.results[1][0] and fake.targets[1].mapping == small
    assert rig.workflow.busy.labels == []
