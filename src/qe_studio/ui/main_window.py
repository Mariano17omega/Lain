"""Main window: full-height layout from the mockups (PRD §2.1).

``ActivityBar | QSplitter[ left panel (explorer ⇄ plot parameters) | file grid | workspace ]``
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import ConfigError, LoadedConfig, load_config
from ..core.detection import FolderMemory
from ..core.sync.monitor import ConnectionMonitor
from .file_types import viewer_kind
from .services import DetectionService
from .theme.manager import ThemeManager
from .widgets.bars import ActivityBar, StatusBar, TopBar
from .widgets.common import PanelHeader
from .widgets.explorer import ExplorerPanel
from .widgets.file_grid import FilePanel
from .widgets.workspace import Workspace

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        loaded: LoadedConfig,
        theme: ThemeManager,
        settings: QSettings | None = None,
        memory: FolderMemory | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.loaded = loaded
        self.theme = theme
        self.settings = settings or QSettings()
        self.memory = memory or FolderMemory()
        self.service = DetectionService(self.memory, self)
        self.monitor = ConnectionMonitor(self.config.cluster, self.config.sync_enabled, self)

        self._build()
        self._build_menus()
        self._connect()
        self._restore_state()
        self._apply_cluster_label(self.monitor.state.value)
        self.on_folder_selected(self.root)
        for warning in loaded.warnings:
            log.warning(warning)
        if loaded.warnings:
            self.status.set_message(loaded.warnings[0], "warning")
        self.monitor.start()

    # -- properties ---------------------------------------------------------------------------------
    @property
    def config(self):
        return self.loaded.config

    @property
    def root(self) -> Path:
        return self.config.paths.local_root

    # -- construction -----------------------------------------------------------------------------
    def _build(self) -> None:
        self.setWindowTitle(f"QE Studio v{__version__} — [Projeto: {self.root}]")
        self.resize(1440, 900)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.top_bar = TopBar(self.theme)
        outer.addWidget(self.top_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.activity = ActivityBar(self.theme)
        body.addWidget(self.activity)

        hidden = self.config.ui.hidden_dirs
        self.explorer = ExplorerPanel(self.theme, self.service, self.root, hidden)
        self.left = QStackedWidget()
        self.left.setObjectName("leftPanel")
        self.left.setMinimumWidth(200)
        self.left.addWidget(self.explorer)
        self.params_page = self._build_params_page()
        self.left.addWidget(self.params_page)

        self.files = FilePanel(self.theme, self.service, self.root, hidden)
        self.files.setMinimumWidth(170)
        self.workspace = Workspace(self.theme)
        self.workspace.setMinimumWidth(320)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        for widget in (self.left, self.files, self.workspace):
            self.splitter.addWidget(widget)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setSizes([280, 320, 840])
        body.addWidget(self.splitter, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        self.status = StatusBar()
        self.setStatusBar(self.status)

    def _build_params_page(self) -> QWidget:
        """Placeholder until a plot exists (replaced by the plot parameters panel)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(PanelHeader(self.theme, "Ajuste do gráfico", "tune"))
        hint = QLabel("Gere um gráfico para ajustar\nos parâmetros de plotagem.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setProperty("variant", "fieldLabel")
        layout.addWidget(hint, 1)
        return page

    def _action(self, menu, text: str, slot, shortcut: str | None = None) -> QAction:
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        files = bar.addMenu("Arquivo")
        self._action(files, "Atualizar", self.refresh, "F5")
        self._action(files, "Abrir pasta no gerenciador de arquivos", self.open_folder_externally)
        files.addSeparator()
        self._action(files, "Sair", self.close, "Ctrl+Q")
        cluster = bar.addMenu("Cluster")
        self.sync_action = self._action(cluster, "Sincronizar pasta selecionada", self.start_sync)
        self._action(cluster, "Testar conexão", self.monitor.check)
        plots = bar.addMenu("Gráficos")
        self._action(plots, "Gerar gráfico", self.generate_plot, "Ctrl+G")
        self.export_action = self._action(plots, "Exportar gráfico", self.export_plot, "Ctrl+E")
        tools = bar.addMenu("Ferramentas")
        self._action(tools, "Alternar tema", self.toggle_theme, "Ctrl+T")
        tools.addSeparator()
        self._action(tools, "Abrir config.yaml", self.open_config)
        self._action(tools, "Recarregar config.yaml", self.reload_config)
        self.sync_action.setEnabled(self.config.sync_enabled)

    def _connect(self) -> None:
        self.explorer.folder_selected.connect(self.on_folder_selected)
        self.explorer.file_selected.connect(self.files.select_file)
        self.explorer.file_activated.connect(self.open_file)
        self.files.file_activated.connect(self.open_file)
        self.files.folder_activated.connect(self.explorer.select_path)
        self.files.file_selected.connect(lambda p: self.status.set_path(self._relative(p)))
        self.activity.explorer_requested.connect(lambda: self.set_left_mode("tree"))
        self.activity.params_requested.connect(lambda: self.set_left_mode("params"))
        self.activity.grid_toggled.connect(lambda on: self.set_panel_visible("grid", on))
        self.activity.plot_requested.connect(self.generate_plot)
        self.activity.sync_requested.connect(self.start_sync)
        self.activity.theme_requested.connect(self.toggle_theme)
        self.top_bar.generate_requested.connect(self.generate_plot)
        self.top_bar.panel_toggled.connect(self.set_panel_visible)
        self.monitor.state_changed.connect(self._apply_cluster_label)

    # -- state ----------------------------------------------------------------------------------
    def _restore_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        sizes = self.settings.value("window/splitter")
        if sizes:
            self.splitter.setSizes([int(s) for s in sizes])
        grid_visible = self.settings.value("window/grid_visible", True, type=bool)
        self.set_panel_visible("grid", grid_visible)

    def _save_state(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/splitter", self.splitter.sizes())
        self.settings.setValue("window/grid_visible", self.files.isVisible())
        self.settings.setValue("ui/theme", self.theme.name)
        self.settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_state()
        self.monitor.stop()
        self.service.wait(2000)
        super().closeEvent(event)

    # -- navigation -----------------------------------------------------------------------------
    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root)) or "."
        except ValueError:
            return str(path)

    def current_folder(self) -> Path:
        return self.explorer.current_folder()

    def on_folder_selected(self, folder: Path) -> None:
        if folder != self.files.folder:
            self.files.set_folder(folder)
        self.top_bar.set_path(folder)
        self.status.set_path(self._relative(folder))

    def open_file(self, path: Path) -> None:
        kind = viewer_kind(path)
        if kind == "external":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        self.workspace.open_file(path, kind)
        self.set_panel_visible("workspace", True)

    def open_folder_externally(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_folder())))

    def refresh(self) -> None:
        self.service.invalidate()
        self.explorer.refresh()
        self.files.refresh()
        self.status.set_message("Atualizado.", timeout_ms=2500)

    def set_left_mode(self, mode: str) -> None:
        self.left.setCurrentIndex(1 if mode == "params" else 0)
        self.activity.set_left_mode(mode)
        self.set_panel_visible("tree", True)

    def set_panel_visible(self, panel: str, visible: bool) -> None:
        widget = {"tree": self.left, "grid": self.files, "workspace": self.workspace}[panel]
        widget.setVisible(visible)
        toggle = self.top_bar.toggles[panel]
        toggle.blockSignals(True)
        toggle.setChecked(visible)
        toggle.blockSignals(False)
        if panel == "grid":
            self.activity.grid.blockSignals(True)
            self.activity.grid.setChecked(visible)
            self.activity.grid.blockSignals(False)

    # -- theme & config -------------------------------------------------------------------------
    def toggle_theme(self) -> None:
        name = self.theme.toggle()
        self.settings.setValue("ui/theme", name)
        self.status.set_message(f"Tema {'escuro' if name == 'dark' else 'claro'}.", timeout_ms=2000)

    def open_config(self) -> None:
        if self.loaded.path is None:
            QMessageBox.information(
                self,
                "config.yaml",
                "Nenhum config.yaml carregado. Copie config.example.yaml para config.yaml "
                "e reinicie o QE Studio.",
            )
            return
        self.open_file(self.loaded.path)

    def reload_config(self) -> None:
        try:
            loaded = load_config(self.loaded.path)
        except ConfigError as exc:
            QMessageBox.critical(self, "config.yaml inválido", str(exc))
            return
        self.loaded = loaded
        self.monitor.stop()
        self.monitor = ConnectionMonitor(self.config.cluster, self.config.sync_enabled, self)
        self.monitor.state_changed.connect(self._apply_cluster_label)
        self._apply_cluster_label(self.monitor.state.value)
        self.monitor.start()
        self.sync_action.setEnabled(self.config.sync_enabled)
        self.explorer.proxy.hidden_dirs = [p.lower() for p in self.config.ui.hidden_dirs]
        self.explorer.set_root(self.root)
        self.files.set_folder(self.root)
        self.setWindowTitle(f"QE Studio v{__version__} — [Projeto: {self.root}]")
        self.refresh()
        message = loaded.warnings[0] if loaded.warnings else "config.yaml recarregado."
        self.status.set_message(message, "warning" if loaded.warnings else "info", 5000)

    def _apply_cluster_label(self, state: str) -> None:
        cluster = self.config.cluster
        label = (
            f"{cluster.user}@{cluster.host}" if cluster.configured else "cluster não configurado"
        )
        self.top_bar.set_cluster(label, state)
        self.activity.rsync.set_dot(None if state == "disabled" else state)

    # -- actions implemented by the plot and sync workflows ----------------------------------------
    def generate_plot(self) -> None:
        self.status.set_message("Geração de gráficos ainda não disponível.", "warning", 3000)

    def export_plot(self) -> None:
        self.status.set_message("Nenhum gráfico aberto.", "warning", 3000)

    def start_sync(self) -> None:
        self.status.set_message("Sincronização ainda não disponível.", "warning", 3000)
