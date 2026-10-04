"""Main window: full-height layout from the mockups (PRD §2.1).

``ActivityBar | QSplitter[ left panel (explorer ⇄ plot parameters) | file grid | workspace ]``

The window is the composition root (spec 15 R4): it builds the widgets and three controllers,
``LayoutController`` (panels and window state), ``PlotWorkflow`` (detect → plot → export) and
``SyncCoordinator`` (cluster pull), plus the help, command palette and first-run controllers
(spec 18), registers the actions and wires the signals. It keeps only what touches several of
them: renaming, reloading the config and closing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QPoint, QSettings, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core.compounds import CompoundStore
from ..core.config import ConfigError, LoadedConfig, load_config
from ..core.file_kinds import viewer_kind
from ..core.file_ops import rename_item
from ..core.folder_memory import FolderMemory
from ..core.nav_store import NavigationStore
from .actions import build_menus
from .calc_create_controller import CalcCreateController
from .derive_controller import DeriveController
from .dialogs.open_many import MANY_FILES, ask_open_many
from .dialogs.rename import ask_rename
from .first_run import FirstRunController
from .focus_controller import FocusController
from .grids_controller import GridsController
from .help_controller import HelpController
from .layout_controller import LayoutController
from .navigation_controller import NavigationController
from .palette_controller import PaletteController
from .plot_settings import PlotSettingsStore
from .plot_workflow import PlotWorkflow
from .services import DetectionService
from .sync_coordinator import SyncCoordinator
from .theme.manager import ThemeManager
from .widgets.bars import ActivityBar, StatusBar, TopBar
from .widgets.context_menu import ItemActions
from .widgets.explorer import ExplorerPanel
from .widgets.file_grid import FilePanel
from .widgets.plot_params import ParamsPanel
from .widgets.plot_view import PlotView
from .widgets.toast import Toast
from .widgets.workspace import Workspace

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    # Relayed from the controllers: scripts and tests wait on the window.
    plot_ready = pyqtSignal(object)  # PlotSession
    plot_failed = pyqtSignal(str)
    export_finished = pyqtSignal(object)  # list[Path]
    sync_finished = pyqtSignal(object)  # SyncReport

    def __init__(
        self,
        loaded: LoadedConfig,
        theme: ThemeManager,
        settings: QSettings | None = None,
        memory: FolderMemory | None = None,
        navigation: NavigationStore | None = None,
        compounds: CompoundStore | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.loaded = loaded
        self.theme = theme
        self.settings = settings or QSettings()
        self.memory = memory or FolderMemory()
        self.navigation_store = navigation or NavigationStore()
        self.compounds = compounds or CompoundStore()  # atoms chosen per compound (spec 21)
        self.memory.set_root(self.root)  # its keys are relative to the project root
        self.service = DetectionService(self.memory, self)
        self.service.paranoid_refresh = self.config.ui.paranoid_refresh
        self._actions: dict[str, QAction] = {}  # by stable id (spec 18 reads it)

        self._build()
        self._build_controllers()
        self._build_menus()
        self._connect()
        self.panel_layout.restore()
        self.sync.start_monitor()
        self._restore_folder()
        self.first_run.refresh()
        for warning in loaded.warnings:
            log.warning(warning)
        # A corrupt folders.json or navigation.json is set aside once: say so before any config warning.
        stored = self.memory.load_warning() or self.navigation_store.load_warning()
        if warning := stored or next(iter(loaded.warnings), None):
            self.status.set_message(warning, "warning")

    # -- properties ---------------------------------------------------------------------------------
    @property
    def config(self):
        return self.loaded.config

    @property
    def root(self) -> Path:
        return self.config.paths.local_root

    @property
    def monitor(self):
        return self.sync.monitor

    # -- construction -----------------------------------------------------------------------------
    def _build(self) -> None:
        self.setWindowTitle(f"{APP_NAME} v{__version__} — [Projeto: {self.root}]")
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
        self.params = ParamsPanel(self.theme, settings=self.settings)
        self.left.addWidget(self.params)
        self.files = FilePanel(self.theme, self.service, self.root, hidden)
        self.files.setMinimumWidth(170)
        self.workspace = Workspace(self.theme)
        self.workspace.setMinimumWidth(320)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        body.addWidget(self.splitter, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        self.status = StatusBar(self.theme)
        self.setStatusBar(self.status)
        self.toast = Toast(self.theme, self, footer=self.status)  # notices, e.g. a pull's end

    def _build_controllers(self) -> None:
        panels = {"tree": self.left, "grid": self.files, "workspace": self.workspace}
        self.panel_layout = LayoutController(
            self, self.splitter, panels, self.top_bar, self.activity, self.settings, self
        )
        self.navigation = NavigationController(
            self,
            self.explorer,
            self.top_bar,
            self.root,
            self.navigation_store,
            self.settings,
            parent=self,
        )
        self.item_actions = ItemActions(self, self.service, self.navigation.is_favorite)
        self.plot_settings = PlotSettingsStore(self)
        self.plot_workflow = PlotWorkflow(
            service=self.service,
            workspace=self.workspace,
            params=self.params,
            memory=self.memory,
            settings=self.plot_settings,
            status=self.status,
            theme=self.theme,
            config=lambda: self.config,
            dialog_parent=self,
            compounds=self.compounds,
            parent=self,
        )
        self.sync = SyncCoordinator(self.config, self.theme, self, self)
        self.help = HelpController.for_window(self)
        self.command_palette = PaletteController.for_window(self)
        self.first_run = FirstRunController.for_window(self)
        self.focus_areas = FocusController.for_window(self)  # tab order and Ctrl+1..4
        self.grids = GridsController.for_window(self)  # "Grids" button and window (spec 23)
        self.derive = DeriveController.for_window(self)  # "Gerar SCF convergido" (spec 24)
        self.calc_create = CalcCreateController.for_window(self)  # "Criar cálculo" (spec 26)

    def _build_menus(self) -> None:
        self._actions = build_menus(self)
        self.sync.bind_actions(self._actions["sync.start"], self._actions["sync.project"])

    def _connect(self) -> None:
        self.explorer.folder_selected.connect(self.on_folder_selected)
        self.explorer.file_selected.connect(self.files.select_file)
        self.explorer.file_activated.connect(self.open_file)
        self.files.file_activated.connect(self.open_file)
        self.files.folder_activated.connect(self.explorer.select_path)
        self.files.file_selected.connect(self._on_file_selected)
        self.files.selection_changed.connect(self._on_selection_changed)
        self.files.files_activated.connect(self.open_files)
        self.explorer.item_menu_requested.connect(self._show_item_menu)
        self.files.item_menu_requested.connect(self._show_item_menu)
        self.item_actions.message.connect(self.status.set_message)
        self.item_actions.rename_requested.connect(self.rename_path)
        self.item_actions.plot_file_requested.connect(self.plot_file)
        self.item_actions.summary_requested.connect(self.open_summary)
        self.item_actions.compare_requested.connect(self.compare_inputs)
        self.item_actions.bands_dos_requested.connect(self.plot_workflow.plot_pair)
        self.item_actions.favorite_toggled.connect(self.navigation.set_favorite)
        self.activity.plot_requested.connect(self.toggle_plot)
        self.activity.sync_requested.connect(self.start_sync)
        self.activity.theme_requested.connect(self.toggle_theme)
        self.top_bar.generate_requested.connect(self.generate_plot)
        self.top_bar.plot_file_requested.connect(self.plot_workflow.plot_open_file)
        self.workspace.external_open_requested.connect(self.item_actions.open_default)
        self.workspace.reveal_requested.connect(self.reveal_in_explorer)
        self.params.back_requested.connect(self.panel_layout.show_tree)
        self.params.generate_requested.connect(self.generate_plot)
        layout, workflow, sync = self.panel_layout, self.plot_workflow, self.sync
        layout.workspace_visibility_changed.connect(workflow.update_readout)
        workflow.panel_requested.connect(self._show_panel)
        workflow.message.connect(self.status.set_message)
        workflow.plot_file_available.connect(self.top_bar.plot_file.setVisible)
        workflow.export_finished.connect(self._on_exported)
        workflow.export_finished.connect(self.export_finished)
        workflow.plot_ready.connect(self.plot_ready)
        workflow.plot_failed.connect(self.plot_failed)
        self.navigation.message.connect(self.status.set_message)
        self.help.message.connect(self.status.set_message)
        self.first_run.message.connect(self.status.set_message)
        self.focus_areas.message.connect(self.status.set_message)
        sync.cluster_changed.connect(self.top_bar.set_cluster)
        sync.cluster_changed.connect(self.activity.set_cluster)
        sync.message.connect(self.status.set_message)
        sync.notice.connect(self.toast.show_message)
        sync.scope_changed.connect(self.activity.set_sync_tooltip)
        sync.synced.connect(self._on_synced)
        sync.finished.connect(self.sync_finished)

    # -- state ----------------------------------------------------------------------------------
    def _restore_folder(self) -> None:
        """Select the folder used last, if it still exists inside the project."""
        last = self.settings.value("explorer/last_folder", "", type=str)
        folder = Path(last) if last else None
        root = self.root.resolve()
        if folder is not None and folder.is_dir() and folder.resolve().is_relative_to(root):
            self.explorer.select_path(folder)
            if self.files.folder == folder:
                return
        self.on_folder_selected(self.root)

    def focusNextPrevChild(self, next: bool) -> bool:
        """Tab and Shift+Tab: the order of the window's regions, rebuilt first (spec 19 R4.3)."""
        self.focus_areas.apply_tab_order()
        return super().focusNextPrevChild(next)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.sync.shutdown()
        self.plot_workflow.shutdown()  # waits for exports: no half-written plots
        self.plot_settings.flush_now()  # on the spot: the app is leaving
        self.plot_settings.shutdown()
        self.panel_layout.save()
        self.navigation.shutdown()
        self.settings.setValue("explorer/last_folder", str(self.current_folder()))
        self.settings.setValue("ui/theme", self.theme.mode)
        self.settings.sync()
        self.service.shutdown(2000)
        self.files.shutdown()  # last: the panels' filters stop (current_folder needs them above)
        self.explorer.shutdown()
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
        self.navigation.visited(folder)
        self.sync.show_scope(folder)
        self.status.set_path(self._relative(folder))

    def _on_file_selected(self, path: Path) -> None:
        if len(self.files.selected_paths()) <= 1:  # a selection of several has its own text
            self.status.set_path(self._relative(path))

    def _on_selection_changed(self, paths: list[Path]) -> None:
        """Footer of the grid selection (spec 16 R5.3): the count for several items."""
        if len(paths) > 1:
            self.status.set_path(f"{len(paths)} itens selecionados")
        else:
            self.status.set_path(self._relative(paths[0] if paths else self.files.folder))

    def open_file(self, path: Path) -> None:
        kind = viewer_kind(path)
        if kind == "external":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        self.workspace.open_file(path, kind)
        self.set_panel_visible("workspace", True)

    def open_files(self, paths: list[Path]) -> None:
        """Enter on a selection: every file opens in the workspace (folders are skipped); more
        than ``MANY_FILES`` ask first (spec 16 R5.4)."""
        files = [path for path in paths if not path.is_dir()]
        if len(files) > MANY_FILES and not ask_open_many(self, len(files)):
            return
        for path in files:
            self.open_file(path)

    def reveal_in_explorer(self, path: Path) -> None:
        """Tab menu "Revelar no explorador": select the item in the tree and the grid."""
        self.set_left_mode("tree")
        self.set_panel_visible("grid", True)
        self.explorer.select_path(path)

    def set_left_mode(self, mode: str) -> None:
        self.panel_layout.set_left_mode(mode)

    def set_panel_visible(self, panel: str, visible: bool) -> None:
        self.panel_layout.set_panel_visible(panel, visible)

    def _show_panel(self, name: str) -> None:
        if name == "params":
            self.set_left_mode("params")
        else:
            self.set_panel_visible(name, True)

    def open_folder_externally(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_folder())))

    def refresh(self) -> None:
        self.service.invalidate()
        self.command_palette.invalidate()  # its folder index is rebuilt on the next open
        self.explorer.refresh()
        self.files.refresh()
        self.status.set_message("Atualizado.", timeout_ms=2500)

    # -- context menu (spec 5 R3) -------------------------------------------------------------------
    def _show_item_menu(self, paths: list[Path], pos: QPoint) -> None:
        self.item_actions.show(paths, pos, can_rename=paths != [self.root])

    def compare_inputs(self, a: Path, b: Path) -> None:
        """ "Comparar" of two selected inputs: the diff tab (spec 16 R5.5)."""
        self.workspace.open_diff(a, b)
        self.set_panel_visible("workspace", True)

    def open_summary(self, path: Path) -> None:
        """ "Resumo" of a QE output: a tab in the workspace (spec 12)."""
        self.workspace.open_summary(path)
        self.set_panel_visible("workspace", True)

    def rename_path(self, path: Path) -> None:
        """Rename a file or folder; tabs showing anything inside it are closed (spec 5 R3.4)."""
        name = ask_rename(self, path)
        if name is None:
            return

        def inside(other: Path) -> bool:
            return other.is_relative_to(path)

        # Pending plot settings go into the folder before it moves, so they travel with it, and
        # an export still writing there must not recreate the old folder afterwards.
        self.plot_settings.flush_now(inside=path)
        self.plot_workflow.wait_for_exports()
        current = self.current_folder()
        tree_had_it = self.explorer.current_path() == path
        old_resolved = path.resolve()
        try:
            new = rename_item(path, name)
        except OSError as exc:
            log.warning("rename %s → %s failed: %s", path, name, exc)
            QMessageBox.warning(
                self, "Renomear", f"Não foi possível renomear {path.name}: {exc.strerror or exc}"
            )
            return
        self.workspace.close_tabs_under(path)
        self.navigation.rename(path, new)
        self.memory.rename(old_resolved, new.resolve())
        self.grids.rename(old_resolved, new.resolve())
        self.service.invalidate(path.parent)
        if inside(current):
            self.explorer.select_path(new / current.relative_to(path))
        elif tree_had_it:
            self.explorer.select_path(new)
        if new.parent == self.files.folder:
            self.files.select_file(new)
        self.status.set_message(f"Renomeado: {path.name} → {new.name}", timeout_ms=4000)

    # -- plots (PlotWorkflow) -----------------------------------------------------------------------
    def toggle_plot(self) -> None:
        """Activity bar "Plot": the first click shows the plot and its settings, the next hides
        them (the left panel goes back to the tree)."""
        if self.panel_layout.plot_shown():
            self.set_panel_visible("workspace", False)
            self.set_left_mode("tree")
        else:
            self.plot_workflow.preview(self.current_folder())

    def current_plot(self) -> PlotView | None:
        return self.plot_workflow.current_plot()

    def generate_plot(self) -> None:
        self.generate_plot_for(self.current_folder())

    def generate_plot_for(self, folder: Path, auto_export: bool = True) -> None:
        self.plot_workflow.generate(folder, auto_export)

    def plot_file(self, path: Path, kind: str) -> None:
        self.plot_workflow.plot_file(path, kind)

    def export_plot(self) -> bool:
        return self.plot_workflow.export()

    def _on_exported(self, _written: list[Path]) -> None:
        self.files.refresh()

    # -- theme & config -------------------------------------------------------------------------
    def toggle_theme(self) -> None:
        self.settings.setValue("ui/theme", self.theme.toggle())  # the mode, not the concrete theme
        self.status.set_message(f"Tema: {self.theme.label()}.", timeout_ms=2000)

    def open_config(self) -> None:
        if self.loaded.path is None:
            self.first_run.create_config()  # no config to open: offer to create one (spec 18 R5.5)
            return
        self.open_file(self.loaded.path)

    def reload_config(self) -> None:
        self.load_config_file(self.loaded.path)

    def load_config_file(self, path: Path | None) -> None:
        """Load the config at ``path`` (None: look it up again) and apply it to the window."""
        try:
            loaded = load_config(path)
        except ConfigError as exc:
            QMessageBox.critical(self, "config.yaml inválido", str(exc))
            return
        self._apply_loaded(loaded)
        message = loaded.warnings[0] if loaded.warnings else "config.yaml recarregado."
        self.status.set_message(message, "warning" if loaded.warnings else "info", 5000)

    def use_session_root(self, folder: Path) -> None:
        """Browse ``folder`` as the project for this session only: the config file is not written,
        and the next reload goes back to its ``paths.local_root`` (spec 18 R5.2)."""
        paths = self.config.paths.model_copy(update={"local_root": folder})
        config = self.config.model_copy(update={"paths": paths})
        self._apply_loaded(LoadedConfig(config, self.loaded.path, self.loaded.warnings))

    def _apply_loaded(self, loaded: LoadedConfig) -> None:
        old_root = self.root
        self.loaded = loaded
        self.memory.set_root(self.root)
        self.navigation.set_root(self.root)
        self.service.paranoid_refresh = self.config.ui.paranoid_refresh
        self.theme.set_font_scale(self.config.ui.font_scale)
        self.sync.set_config(self.config)
        self.explorer.apply_config(self.root, self.config.ui.hidden_dirs)
        self.files.apply_config(self.root, self.config.ui.hidden_dirs)
        self.setWindowTitle(f"{APP_NAME} v{__version__} — [Projeto: {self.root}]")
        self.refresh()
        if self.root != old_root:  # a new project: start at its top
            self.explorer.select_path(self.root)
        self.first_run.refresh()

    # -- cluster sync (SyncCoordinator) -------------------------------------------------------------
    def start_sync(self) -> None:
        """Pull the selected folder from the cluster (whole project when nothing is selected)."""
        self.sync.start(self.current_folder())

    def start_project_sync(self) -> None:
        """ "Sincronizar projeto inteiro": the root, whatever is selected (spec 17 R1.3)."""
        self.sync.start(self.root)

    def _on_synced(self, local_dir: Path) -> None:
        self.service.invalidate(local_dir)
        self.explorer.refresh()
        self.files.refresh()
