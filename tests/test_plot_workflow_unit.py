"""``PlotWorkflow`` and ``PlotSettingsStore`` without the main window (spec 15 R4.7): real
workspace, parameters panel and status bar, and the detection service."""

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMessageBox, QWidget

from qe_studio.core.config import parse_config
from qe_studio.core.folder_memory import FolderMemory
from qe_studio.core.plotting.plot_file import read_plot_file
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
    assert rig.status.readout.text().startswith("03_bands · E_F = 8.0584 eV")
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
    assert [p.name for p in blocker.args[0]] == ["bands.png", "bands.svg", "bands.pdf"]
    assert ("Salvo em plots/: bands.png, bands.svg, bands.pdf", "info") in rig.messages
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
