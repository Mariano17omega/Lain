"""Main window: full-height layout from the mockups (PRD §2.1).

``ActivityBar | QSplitter[ left panel (explorer ⇄ plot parameters) | file grid | workspace ]``
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import (
    QObject,
    QPoint,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core.calculations import REGISTRY, CalculationModule, DetectionResult, describe_plottable
from ..core.calculations.base import LoadError
from ..core.config import ConfigError, LoadedConfig, load_config
from ..core.detection import FolderMemory, manual_result
from ..core.file_ops import rename_item
from ..core.plotting.export import existing_targets, export_figure, next_free_stem
from ..core.plotting.plot_file import (
    apply_stored,
    delete_plot_file,
    plot_file_path,
    read_plot_file,
    stored_params,
    write_plot_file,
)
from ..core.sync.controller import SyncController, SyncReport, SyncStatus
from ..core.sync.monitor import ConnectionMonitor
from ..core.sync.planner import PlanItem
from ..core.sync.rsync import Endpoint, remote_dir_for
from .dialogs.mapping import ask_mapping
from .dialogs.overwrite import OverwriteChoice, ask_overwrite
from .dialogs.rename import ask_rename
from .dialogs.sync_dialog import ConflictDialog, SyncDialog
from .file_types import viewer_kind
from .plot_session import PlotSession, plot_key
from .services import DetectionService
from .theme.manager import ThemeManager
from .widgets.bars import ActivityBar, StatusBar, TopBar
from .widgets.context_menu import ItemActions
from .widgets.explorer import ExplorerPanel
from .widgets.file_grid import FilePanel
from .widgets.fs_model import SORT_DATE, SORT_NAME, SORT_SIZE
from .widgets.plot_params import ParamsPanel
from .widgets.plot_view import PlotView
from .widgets.workspace import Workspace

log = logging.getLogger(__name__)
RENDER_DEBOUNCE_MS = 120
PLOT_SAVE_DEBOUNCE_MS = 1000
PANELS = ("tree", "grid", "workspace")  # splitter order
DEFAULT_PANEL_WIDTHS = {"tree": 280, "grid": 320, "workspace": 840}


class _Manual(NamedTuple):
    """A manual mapping (PRD §3.2), matched in the load worker: that sniffs the chosen files,
    which can be big or on a network disk."""

    module: CalculationModule
    folder: Path
    mapping: dict[str, list[Path]]
    sniff: Callable

    @property
    def kind(self) -> str:
        return self.module.kind

    def build(self) -> DetectionResult:
        return manual_result(self.module, self.folder, self.mapping, self.sniff)


class _LoadSignals(QObject):
    loaded = pyqtSignal(object, object, object)  # DetectionResult, dataset, read_plot_file()
    failed = pyqtSignal(object, str)  # DetectionResult | _Manual


class _LoadTask(QRunnable):
    def __init__(self, target: DetectionResult | _Manual):
        super().__init__()
        self.target = target
        self.signals = _LoadSignals()
        self.done = False

    def run(self) -> None:
        try:
            target = self.target
            result = target.build() if isinstance(target, _Manual) else target
            dataset = result.module.load_cached(result)
            stored = read_plot_file(result.folder, result.kind)
        except LoadError as exc:
            self.signals.failed.emit(self.target, str(exc))
        except Exception as exc:  # parsing errors must reach the user, not kill the worker
            log.exception("load failed")
            self.signals.failed.emit(self.target, f"{type(exc).__name__}: {exc}")
        else:
            self.signals.loaded.emit(result, dataset, stored)
        finally:
            self.done = True


def choose_result(parent: QWidget, results: list[DetectionResult]) -> DetectionResult | None:
    """Several plottable kinds in one folder (e.g. BANDS + PDOS): ask which one."""
    labels = [r.module.display_name for r in results]
    label, ok = QInputDialog.getItem(parent, "Gerar gráfico", "Tipo de cálculo:", labels, 0, False)
    return results[labels.index(label)] if ok else None


def fit_widths(
    weights: dict[str, int], minimums: dict[str, int], available: int, keep: str | None = None
) -> dict[str, int]:
    """Split ``available`` px among panels in proportion to ``weights``, none below its minimum.

    ``keep`` (a panel shown again) gets its weight as width, reduced until the others fit.
    """
    rest = dict(weights)
    sizes: dict[str, int] = {}
    if keep is not None:
        room = available - sum(minimums[name] for name in rest if name != keep)
        sizes[keep] = max(min(rest.pop(keep), room), minimums[keep])
        available -= sizes[keep]
    while True:
        total = sum(rest.values()) or 1
        pinned = [name for name, w in rest.items() if available * w / total < minimums[name]]
        if not pinned:
            break
        for name in pinned:
            sizes[name] = minimums[name]
            available -= minimums[name]
            del rest[name]
    names = list(rest)
    total = sum(rest.values()) or 1
    for name in names[:-1]:
        sizes[name] = round(available * rest[name] / total)
    if names:  # the last one takes the rounding remainder, so the sum is exact
        sizes[names[-1]] = available - sum(sizes[name] for name in names[:-1])
    return sizes


class MainWindow(QMainWindow):
    plot_ready = pyqtSignal(object)  # PlotSession
    plot_failed = pyqtSignal(str)
    sync_finished = pyqtSignal(object)  # SyncReport

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
        self._loads: dict[str, _LoadTask] = {}
        self._detecting: dict[str, bool] = {}  # folder → auto_export, waiting for detection
        self._overwrite_always = False
        self._sync: SyncController | None = None
        self._sync_dialog: SyncDialog | None = None
        self.conflict_dialog: ConflictDialog | None = None
        self._session_password: str | None = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(RENDER_DEBOUNCE_MS)
        self._render_timer.timeout.connect(self._render_current)
        # Plot settings edited since their last write to <folder>/<kind>.plot, by plot key.
        self._unsaved: dict[str, PlotSession] = {}
        self._save_failed: set[str] = set()  # plot keys already warned about (once per run)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(PLOT_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._flush_plot_files)

        self._build()
        self._build_menus()
        self._connect()
        self._restore_state()
        self._apply_cluster_label(self.monitor.state.value)
        self._restore_folder()
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
        self._panels = {"tree": self.left, "grid": self.files, "workspace": self.workspace}
        for name in PANELS:
            self.splitter.addWidget(self._panels[name])
        # Working width of each panel, kept while it is hidden (spec 1 R3). Sizes set by
        # _apply_panel_layout; while the splitter still shows them, the working widths stand.
        self._panel_widths = dict(DEFAULT_PANEL_WIDTHS)
        self._applied_sizes: list[int] | None = None
        body.addWidget(self.splitter, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        self.status = StatusBar()
        self.setStatusBar(self.status)
        self.item_actions = ItemActions(self)

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
        self._action(cluster, "Testar conexão", self._test_connection)
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
        self.explorer.item_menu_requested.connect(self._show_item_menu)
        self.files.item_menu_requested.connect(self._show_item_menu)
        self.item_actions.message.connect(self._on_item_message)
        self.item_actions.rename_requested.connect(self.rename_path)
        self.activity.explorer_requested.connect(lambda: self.set_left_mode("tree"))
        self.activity.grid_toggled.connect(lambda on: self.set_panel_visible("grid", on))
        self.activity.plot_requested.connect(self.toggle_plot)
        self.activity.sync_requested.connect(self.start_sync)
        self.activity.theme_requested.connect(self.toggle_theme)
        self.top_bar.generate_requested.connect(self.generate_plot)
        self.top_bar.panel_toggled.connect(self.set_panel_visible)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        self.monitor.state_changed.connect(self._apply_cluster_label)
        self.service.detected.connect(self._on_detected)
        self.workspace.current_changed.connect(self._on_tab_changed)
        self.workspace.tab_closing.connect(self._on_tab_closing)
        self.params.changed.connect(self._on_param_changed)
        self.params.back_requested.connect(lambda: self.set_left_mode("tree"))
        self.params.export_requested.connect(self.export_plot)
        self.params.generate_requested.connect(self.generate_plot)
        self.params.remap_requested.connect(self._remap_current)
        self.params.restore_requested.connect(self._restore_defaults)

    # -- state ----------------------------------------------------------------------------------
    def _restore_state(self) -> None:
        settings = self.settings
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        # Keys before spec 3: window/splitter (raw sizes, 0 for hidden panels), window/grid_visible.
        for key in ("layout/panel_widths", "window/splitter"):
            widths = [int(w) for w in settings.value(key, [], type=list)]
            if len(widths) == len(PANELS) and min(widths) > 0:
                self._panel_widths = dict(zip(PANELS, widths, strict=True))
                break
        grid_visible = settings.value("window/grid_visible", True, type=bool)
        settings.remove("window/splitter")
        settings.remove("window/grid_visible")
        self.set_panel_visible("tree", settings.value("layout/tree_visible", True, type=bool))
        self.set_panel_visible(
            "grid", settings.value("layout/grid_visible", grid_visible, type=bool)
        )
        # Tabs are not restored, so the workspace would open empty (spec 1 R1).
        self.set_panel_visible("workspace", False)
        self.files.set_grid_mode(settings.value("files/grid_mode", True, type=bool))
        sort = settings.value("files/sort", SORT_NAME, type=int)
        self.files.set_sort(sort if sort in (SORT_NAME, SORT_SIZE, SORT_DATE) else SORT_NAME)

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

    def _save_state(self) -> None:
        settings = self.settings
        settings.setValue("window/geometry", self.saveGeometry())
        self._sync_panel_widths()
        settings.setValue("layout/panel_widths", [self._panel_widths[n] for n in PANELS])
        settings.setValue("layout/tree_visible", not self.left.isHidden())
        settings.setValue("layout/grid_visible", not self.files.isHidden())
        settings.setValue("files/grid_mode", self.files.grid_mode)
        settings.setValue("files/sort", self.files.sort_column)
        settings.setValue("explorer/last_folder", str(self.current_folder()))
        settings.setValue("ui/theme", self.theme.name)
        settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._sync is not None and self._sync.running:
            self._sync.shutdown()
        self._save_timer.stop()
        self._flush_plot_files()
        self._save_state()
        self.monitor.stop()
        self.service.shutdown(2000)
        self.files.shutdown()
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

    # -- context menu (spec 5 R3) -------------------------------------------------------------------
    def _show_item_menu(self, path: Path, pos: QPoint) -> None:
        menu = self.item_actions.menu(path, can_rename=path != self.root)
        menu.exec(pos)
        menu.deleteLater()

    def _on_item_message(self, text: str, level: str) -> None:
        self.status.set_message(text, level, 4000)

    def rename_path(self, path: Path) -> None:
        """Rename a file or folder; tabs showing anything inside it are closed (spec 5 R3.4)."""
        name = ask_rename(self, path)
        if name is None:
            return

        def inside(other: Path) -> bool:
            return other.is_relative_to(path)

        # Pending plot settings go into the folder before it moves, so they travel with it.
        for key, session in list(self._unsaved.items()):
            if inside(session.folder):
                self._flush_plot_files(key)
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
        for key, widget in self.workspace.items():
            shown = widget.session.folder if isinstance(widget, PlotView) else widget.path
            if inside(shown):
                self.workspace.close_key(key)
        self.memory.rename(old_resolved, new.resolve())
        self.service.invalidate(path.parent)
        if inside(current):
            self.explorer.select_path(new / current.relative_to(path))
        elif tree_had_it:
            self.explorer.select_path(new)
        if new.parent == self.files.folder:
            self.files.select_file(new)
        self.status.set_message(f"Renomeado: {path.name} → {new.name}", timeout_ms=4000)

    def toggle_plot(self) -> None:
        """Activity bar "Plot": the first click shows the plot and its settings, the next hides
        them (the left panel goes back to the tree)."""
        showing = (
            not self.workspace.isHidden()
            and not self.left.isHidden()
            and self.left.currentWidget() is self.params
        )
        if showing:
            self.set_panel_visible("workspace", False)
            self.set_left_mode("tree")
        else:
            self.preview_plot()

    def preview_plot(self) -> None:
        """Plot the selected folder in the workspace without saving it.

        A plot of that folder already open is only brought to front, keeping its edits.
        """
        folder = self.current_folder()
        self.set_panel_visible("workspace", True)
        self.set_left_mode("params")
        view = self.current_plot()
        if view is None or view.session.folder != folder:
            keys = (plot_key(folder, m.kind) for m in REGISTRY if m.plottable)
            view = next((w for w in map(self.workspace.widget_for, keys) if w is not None), None)
        if view is not None:
            self.workspace.set_current(view)
        else:
            self.generate_plot_for(folder, auto_export=False)

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
        widget = self._panels[panel]
        if widget.isHidden() == visible:
            self._sync_panel_widths()
            widget.setVisible(visible)
            self._apply_panel_layout(panel)
        toggle = self.top_bar.toggles[panel]
        toggle.blockSignals(True)
        toggle.setChecked(visible)
        toggle.blockSignals(False)
        if panel == "grid":
            self.activity.grid.blockSignals(True)
            self.activity.grid.setChecked(visible)
            self.activity.grid.blockSignals(False)
        if panel == "workspace":
            self._update_readout()

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self._sync_panel_widths()

    def _sync_panel_widths(self) -> None:
        """Take sizes the user changed (dragged divider, resized window) as working widths.

        While the splitter still shows the sizes set by ``_apply_panel_layout`` the working
        widths stand, so hiding and showing a panel back restores the layout exactly.
        """
        if not self.splitter.isVisible():
            return  # not laid out yet
        sizes = self.splitter.sizes()
        if self._applied_sizes is None:
            # First look after the window was shown: that layout came from the working widths.
            self._applied_sizes = sizes
            return
        if sizes == self._applied_sizes:
            return
        for name, size in zip(PANELS, sizes, strict=True):
            if size > 0:  # hidden panels report 0
                self._panel_widths[name] = size

    def _apply_panel_layout(self, changed: str) -> None:
        """Resize the panels after ``changed`` was shown or hidden (spec 1 R3).

        A hidden panel's space goes to the visible ones in proportion to their widths; a panel
        shown again gets its working width back and the others shrink in proportion.
        """
        shown = [name for name in PANELS if not self._panels[name].isHidden()]
        # The workspace absorbs window resizes; without it (no stretch factor at all) QSplitter
        # shares them in proportion to the panel sizes.
        self.splitter.setStretchFactor(PANELS.index("workspace"), int("workspace" in shown))
        self.splitter.refresh()  # handle visibility now, not on the next LayoutRequest
        widths = {name: self._panel_widths[name] for name in shown}
        visible = self.splitter.isVisible()
        if visible and shown:
            handles = self.splitter.handleWidth() * (len(shown) - 1)
            available = self.splitter.contentsRect().width() - handles
            minimums = {name: self._panels[name].minimumWidth() for name in shown}
            keep = changed if changed in shown else None
            widths = fit_widths(widths, minimums, available, keep)
        # Before the first show the working widths go in as is; the first layout scales them.
        self.splitter.setSizes([widths.get(name, 0) for name in PANELS])
        self._applied_sizes = self.splitter.sizes() if visible else None

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
                "e reinicie o Lain.",
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
        old = self.monitor
        old.stop()
        old.state_changed.disconnect(self._apply_cluster_label)
        old.deleteLater()
        self.monitor = ConnectionMonitor(self.config.cluster, self.config.sync_enabled, self)
        self.monitor.state_changed.connect(self._apply_cluster_label)
        self._apply_cluster_label(self.monitor.state.value)
        self.monitor.start()
        self.sync_action.setEnabled(self.config.sync_enabled)
        for proxy in (self.explorer.proxy, self.files.proxy):
            proxy.set_hidden_dirs(self.config.ui.hidden_dirs)
        self.files.proxy.set_root(self.root)
        self.explorer.set_root(self.root)
        self.files.set_folder(self.root)
        self.setWindowTitle(f"{APP_NAME} v{__version__} — [Projeto: {self.root}]")
        self.refresh()
        message = loaded.warnings[0] if loaded.warnings else "config.yaml recarregado."
        self.status.set_message(message, "warning" if loaded.warnings else "info", 5000)

    def _test_connection(self) -> None:
        self.monitor.check()

    def _apply_cluster_label(self, state: str) -> None:
        cluster = self.config.cluster
        label = (
            f"{cluster.user}@{cluster.host}" if cluster.configured else "cluster não configurado"
        )
        self.top_bar.set_cluster(label, state)
        self.activity.rsync.set_dot(None if state == "disabled" else state)

    # -- plot workflow (PRD §3, §4) -----------------------------------------------------------------
    def current_plot(self) -> PlotView | None:
        widget = self.workspace.current()
        return widget if isinstance(widget, PlotView) else None

    def generate_plot(self) -> None:
        self.generate_plot_for(self.current_folder())

    def generate_plot_for(self, folder: Path, auto_export: bool = True) -> None:
        """Detect → (choose / map manually) → load in a worker → plot tab → save to plots/.

        Detection runs in the service pool (big outputs, network disks): the rest continues
        in ``_on_detected``.
        """
        key = str(folder)
        if key in self._detecting:
            return
        self._detecting[key] = auto_export
        self.status.set_message("Detectando cálculo…")
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        self.service.request(Path(folder), fresh=True)

    def _on_detected(self, key: str) -> None:
        if key not in self._detecting:
            return
        # Taken now: by the next loop turn a refresh or sync may have invalidated the cache.
        results = self.service.results(Path(key))
        if results is None:
            return  # invalidated already: detection runs again and lands here
        auto_export = self._detecting.pop(key)
        QApplication.restoreOverrideCursor()
        self.status.set_message("")
        # Next loop turn: dialogs below must not run inside the detection task's signal.
        QTimer.singleShot(0, lambda: self._plot_detected(Path(key), results, auto_export))

    def _plot_detected(
        self, folder: Path, results: list[DetectionResult], auto_export: bool
    ) -> None:
        plottable = [r for r in results if r.module.plottable]
        complete = [r for r in plottable if r.complete]
        if len(complete) > 1:
            chosen = choose_result(self, complete)
            if chosen is None:
                return
        elif complete:
            chosen = complete[0]
        else:
            chosen = self._map_manually(folder, results)
            if chosen is None:
                return
        self._load(chosen, auto_export)

    def _map_manually(self, folder: Path, results: list[DetectionResult]) -> _Manual | None:
        modules = [m for m in REGISTRY if m.plottable]
        detected = [r.badge for r in results if not r.module.plottable]
        message = ""
        if detected and not any(r.module.plottable for r in results):
            message = (
                f"Esta pasta foi identificada como {', '.join(detected)}, que não tem gráfico "
                f"próprio. Para plotar {describe_plottable()}, indique os arquivos."
            )
        elif not results:
            message = (
                "Nenhum cálculo reconhecido nesta pasta (nomes e conteúdo). "
                "Indique o tipo de cálculo e os arquivos manualmente."
            )
        answer = ask_mapping(self, folder, modules, results, message)
        if answer is None:
            return None
        kind, mapping, remember = answer
        module = next(m for m in modules if m.kind == kind)
        if remember:
            self.memory.set_mapping(folder, kind, mapping)
            self.service.invalidate(folder)
        return _Manual(module, folder, mapping, self.service.sniff_cache.sniff)

    def _load(self, target: DetectionResult | _Manual, auto_export: bool) -> None:
        key = plot_key(target.folder, target.kind)
        if key in self._loads and not self._loads[key].done:
            return
        self._flush_plot_files(key)  # the worker reads the .plot: pending edits first
        task = _LoadTask(target)
        task.signals.loaded.connect(lambda r, d, s: self._on_loaded(r, d, s, auto_export))
        task.signals.failed.connect(self._on_load_failed)
        self._loads[key] = task
        self.status.set_message(f"Carregando {target.module.display_name.lower()}…")
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        QThreadPool.globalInstance().start(task)

    def _finish_load(self, target: DetectionResult | _Manual) -> None:
        # Released on the next loop turn: we are inside a slot of the task's own signal object.
        key = plot_key(target.folder, target.kind)
        QTimer.singleShot(0, lambda: self._loads.pop(key, None))
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def _on_load_failed(self, target: DetectionResult | _Manual, error: str) -> None:
        self._finish_load(target)
        self.status.set_message("Falha ao carregar os dados do gráfico.", "error", 8000)
        QMessageBox.warning(self, "Não foi possível gerar o gráfico", error)
        self.plot_failed.emit(error)

    def _on_loaded(self, result: DetectionResult, dataset, stored, auto_export: bool) -> None:
        self._finish_load(result)
        key = plot_key(result.folder, result.kind)
        existing = self.workspace.widget_for(key)
        module = result.module
        params = module.default_params(self.config, dataset)
        stored, stored_warnings = stored
        if existing is not None and existing.session.params != existing.session.defaults:
            # Regenerating an open plot: its tab also has the edits made while the worker read
            # <kind>.plot (they reach the file only when the tab closes below).
            stored, stored_warnings = stored_params(existing.session.params), []
        if stored is None:  # settings kept in FolderMemory before <kind>.plot existed
            module.legacy_params(params, result.folder, self.memory)
        session = PlotSession(result, dataset, params)  # defaults: without the stored settings
        if stored is not None:
            ignored = apply_stored(params, stored, module.param_schema(dataset))
            if ignored:
                log.warning("%s.plot: ignored %s", result.kind, ", ".join(ignored))
        if existing is not None:
            self.workspace.close_key(key)
        view = PlotView(self.theme, session)
        view.rendered.connect(self._on_rendered)
        view.limits_changed.connect(self._on_limits_changed)
        view.export_requested.connect(self.export_plot)
        self.workspace.add(key, view, session.title, ("bubble_chart", "accent"), str(result.folder))
        self.set_panel_visible("workspace", True)  # workspace.add made the tab current: bound
        self.set_left_mode("params")
        self.status.set_message(
            f"{session.module.display_name}: {result.folder.name}", timeout_ms=4000
        )
        if stored_warnings:
            self.status.set_message(stored_warnings[0], "warning", 8000)
        if auto_export:
            self.export_plot()
        self.plot_ready.emit(session)

    def _on_tab_changed(self, widget) -> None:
        if isinstance(widget, PlotView):
            self.params.bind(widget.session)
        elif widget is None:
            self.params.bind(None)
        self._update_readout()

    def _on_param_changed(self, _name: str) -> None:
        self._render_timer.start()
        if self.params.session is not None:
            self._mark_unsaved(self.params.session)

    def _on_limits_changed(self) -> None:
        # Pan/zoom or Reset in the plot toolbar (always the visible, current plot).
        self.params.refresh_values()
        view = self.current_plot()
        if view is not None:
            self._mark_unsaved(view.session)

    # -- plot settings files (<folder>/<kind>.plot) ---------------------------------------------
    def _mark_unsaved(self, session: PlotSession) -> None:
        self._unsaved[session.key] = session
        self._save_timer.start()

    def _flush_plot_files(self, key: str | None = None) -> None:
        """Write the pending settings (all, or only the plot ``key``)."""
        keys = list(self._unsaved) if key is None else [key]
        for session in filter(None, (self._unsaved.pop(k, None) for k in keys)):
            try:
                write_plot_file(session.folder, session.kind, session.params)
            except OSError as exc:
                log.warning("cannot save %s.plot in %s: %s", session.kind, session.folder, exc)
                if session.key not in self._save_failed:
                    self._save_failed.add(session.key)
                    self.status.set_message(
                        f"Não foi possível salvar {session.kind}.plot em {session.folder.name}: "
                        f"{exc.strerror or exc}",
                        "warning",
                        8000,
                    )

    def _on_tab_closing(self, widget) -> None:
        if isinstance(widget, PlotView):
            self._flush_plot_files(widget.session.key)
            self.params.discard(widget.session.key)

    def _restore_defaults(self) -> None:
        session = self.params.session
        if session is None:
            return
        name = plot_file_path(session.folder, session.kind).name
        answer = QMessageBox.question(
            self,
            "Restaurar padrões",
            f"Voltar todos os ajustes deste gráfico ao padrão e apagar {name}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._unsaved.pop(session.key, None)
        session.params = copy.deepcopy(session.defaults)
        try:
            delete_plot_file(session.folder, session.kind)
        except OSError as exc:
            self.status.set_message(f"Não foi possível apagar {name}: {exc}", "warning", 8000)
        self.params.bind(session)
        view = self.workspace.widget_for(session.key)
        if view is not None:
            view.render()

    def _render_current(self) -> None:
        view = self.current_plot()
        if view is not None:
            view.render()

    def _on_rendered(self, _info) -> None:
        # Any open plot re-renders on a theme change: show what the current one says.
        self._update_readout()
        view = self.current_plot()
        if view is not None and view.session is self.params.session and view.session.info:
            self.params.update_readout()

    def _update_readout(self) -> None:
        """Footer summary of the plot on screen, empty when none is (spec 1 R6)."""
        view = None if self.workspace.isHidden() else self.current_plot()
        info = view.session.info if view is not None else None
        if info is None:
            self.status.set_readout("")
            return
        params = view.session.params
        dpi = params.export_dpi
        px = f"{round(params.figure_width * dpi)}×{round(params.figure_height * dpi)} px"
        name = view.session.folder.name
        self.status.set_readout(f"{name} · {info.summary} · {px} ({dpi} DPI)")

    def _remap_current(self) -> None:
        view = self.current_plot()
        if view is None:
            return
        folder = view.session.folder
        result = self._map_manually(folder, [view.session.result])
        if result is not None:
            self._load(result, auto_export=False)

    def export_plot(self) -> list[Path]:
        """Save the current plot to <folder>/plots/ in the configured formats (PRD §4.4)."""
        view = self.current_plot()
        if view is None:
            self.status.set_message("Nenhum gráfico aberto.", "warning", 3000)
            return []
        session = view.session
        params = session.params
        formats = params.export_formats
        if not formats:
            self.status.set_message("Selecione ao menos um formato de exportação.", "warning", 4000)
            return []
        stem = session.module.export_stem(params)
        existing = existing_targets(session.folder, stem, formats)
        if existing and not self._overwrite_always:
            new_stem = next_free_stem(session.folder, stem, formats)
            choice, remember = ask_overwrite(self, existing, new_stem)
            if choice is OverwriteChoice.CANCEL:
                self.status.set_message("Exportação cancelada.", timeout_ms=3000)
                return []
            if choice is OverwriteChoice.NEW_VERSION:
                stem = new_stem
            self._overwrite_always = remember
        try:
            written = export_figure(
                session.module, session.dataset, params, session.style, session.folder, stem
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Falha ao exportar", str(exc))
            return []
        names = ", ".join(p.name for p in written)
        self.status.set_message(f"Salvo em plots/: {names}", timeout_ms=8000)
        self.files.refresh()
        return written

    # -- cluster sync (PRD §5) ----------------------------------------------------------------------
    def start_sync(self) -> None:
        """Pull the selected folder from the cluster (whole project when nothing is selected)."""
        if self._sync is not None and self._sync.running:
            return
        if not self.config.sync_enabled:
            QMessageBox.information(
                self,
                "Sincronização",
                "Configure cluster.host, cluster.user e paths.remote_root no config.yaml "
                "para sincronizar.",
            )
            return
        folder = self.current_folder()
        try:
            remote_dir = remote_dir_for(folder, self.config)
        except ValueError as exc:
            QMessageBox.warning(self, "Sincronização", str(exc))
            return
        password = None
        cluster = self.config.cluster
        if cluster.auth == "password" and cluster.resolve_password() is None:
            password = self._ask_password()
            if password is None:
                return
        endpoint = Endpoint(remote_dir, cluster.host, cluster.user)
        self._run_sync(folder, endpoint, password)

    def _ask_password(self) -> str | None:
        if self._session_password:
            return self._session_password
        cluster = self.config.cluster
        text, ok = QInputDialog.getText(
            self,
            "Senha do cluster",
            f"Senha de {cluster.user}@{cluster.host} (não é salva):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not text:
            return None
        self._session_password = text
        return text

    def _run_sync(self, folder: Path, endpoint: Endpoint, password: str | None = None) -> None:
        controller = SyncController(self.config, self, password=password)
        dialog = SyncDialog(self.theme, controller, endpoint.spec(), str(folder), self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        controller.conflict_needed.connect(self._ask_conflict)
        controller.finished.connect(self._on_sync_finished)
        self._sync, self._sync_dialog = controller, dialog
        self.monitor.set_syncing(True)
        dialog.open()
        controller.start(folder, endpoint)

    def _ask_conflict(self, item: PlanItem) -> None:
        parent = self._sync_dialog or self
        dialog = ConflictDialog(item, parent)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.decided.connect(self._sync.resolve)
        dialog.finished.connect(lambda _r: setattr(self, "conflict_dialog", None))
        self.conflict_dialog = dialog
        dialog.open()

    def _on_sync_finished(self, report: SyncReport) -> None:
        # The dialog deletes itself on close; the controller goes on the next loop turn.
        controller, self._sync, self._sync_dialog = self._sync, None, None
        if controller is not None:
            controller.deleteLater()
        self.monitor.set_syncing(False)
        if report.status is not SyncStatus.CANCELLED:
            self.monitor.report(not report.connection_failed)
        if report.status is SyncStatus.FAILED and "Autenticação" in (report.error or ""):
            self._session_password = None
        self.service.invalidate(report.local_dir)
        self.explorer.refresh()
        self.files.refresh()
        title = "Sincronização"
        if report.status is SyncStatus.FAILED:
            QMessageBox.critical(self, title, report.message)
        elif report.status is SyncStatus.LOCAL_NEWER:
            QMessageBox.warning(self, title, report.message)
        elif report.status is SyncStatus.CANCELLED:
            self.status.set_message(report.message, "warning", 5000)
        else:
            QMessageBox.information(self, title, report.message)
            self.status.set_message(report.message.splitlines()[0], timeout_ms=6000)
        self.sync_finished.emit(report)
