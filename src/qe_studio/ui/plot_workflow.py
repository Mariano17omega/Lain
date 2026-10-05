"""The plot workflow (PRD §3, §4): detect → choose or map → load → plot tab → render → export.

``PlotWorkflow`` only orchestrates: the decisions are ``core`` (``plot_choice``, ``load_plot``,
``build_session``; exports go through ``PlotExporter``); it opens the dialogs, runs the workers and
updates the widgets it was given. It never knows the main window: what the window must do (show a
panel, a status message) is a signal.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QWidget

from ..core.calculations import (
    CLOSE_DROP_MIN_BYTES,
    DetectionResult,
    drop_cached,
    module_for,
    module_for_file,
)
from ..core.calculations.base import LoadError, Stores
from ..core.compounds import CompoundStore
from ..core.config import AppConfig
from ..core.detection import (
    Ambiguous,
    Chosen,
    ManualTarget,
    PairTarget,
    mapping_message,
    plot_choice,
    plottable_modules,
)
from ..core.folder_memory import FolderMemory
from ..core.grid_store import GridStore
from ..core.plotting.session import PlotSession, build_session, load_plot, target_key
from ..core.tasks import TaskGroup
from .busy import BusyTracker
from .dialogs.mapping import ask_mapping
from .plot_export import EXPORT_WAIT_MS, PlotExporter
from .plot_settings import PlotSettingsStore
from .services import DetectionService
from .theme.manager import ThemeManager
from .widgets.bars import StatusBar
from .widgets.plot_params import ParamsPanel
from .widgets.plot_view import PlotView
from .widgets.text_viewer import TextViewer
from .widgets.workspace import Workspace

log = logging.getLogger(__name__)
RENDER_DEBOUNCE_MS = 120


def choose_result(parent: QWidget, results: list[DetectionResult]) -> DetectionResult | None:
    """Several plottable kinds in one folder (e.g. BANDS + PDOS): ask which one."""
    labels = [r.module.display_name for r in results]
    label, ok = QInputDialog.getItem(parent, "Gerar gráfico", "Tipo de cálculo:", labels, 0, False)
    return results[labels.index(label)] if ok else None


@dataclass
class _Loading:
    """A plot being loaded: its data first (load pool), then its ``.plot`` (settings queue)."""

    auto_export: bool
    result: DetectionResult | None = None
    dataset: Any = None


class PlotWorkflow(QObject):
    plot_ready = pyqtSignal(object)  # PlotSession, its tab shown
    plot_failed = pyqtSignal(str)
    export_finished = pyqtSignal(object)  # list[Path] written into plots/
    message = pyqtSignal(str, str, int)  # text, level, timeout (ms; 0 = stays)
    panel_requested = pyqtSignal(str)  # "workspace" | "params"
    plot_file_available = pyqtSignal(bool)  # the current tab is an output one module plots alone

    def __init__(
        self,
        *,
        service: DetectionService,
        workspace: Workspace,
        params: ParamsPanel,
        memory: FolderMemory,
        settings: PlotSettingsStore,
        status: StatusBar,
        theme: ThemeManager,
        config: Callable[[], AppConfig],
        dialog_parent: QWidget,
        compounds: CompoundStore | None = None,
        grids: GridStore | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.service, self.workspace, self.params = service, workspace, params
        self.memory, self.settings, self.status, self.theme = memory, settings, status, theme
        # Kept per user, not per folder: atoms per compound, the saved grids and their settings.
        self.stores = Stores(compounds or CompoundStore(), grids or GridStore())
        self._config = config
        self._dialog_parent = dialog_parent
        self._detecting: dict[str, bool] = {}  # folder → auto_export, waiting for detection
        self._loading: dict[str, _Loading] = {}  # by plot key
        self._loads = TaskGroup()  # by plot key, in the global pool
        self._replacing: str | None = None  # key of the tab a new session is about to replace
        self._plot_file_source: tuple[Path, str] | None = None  # what "Plotar SCF" plots
        # Busy indicator (spec 15 R2): counted by name, so a task that never ends cannot leave a
        # global cursor behind; detections, loads and exports all show in the footer.
        self.busy = BusyTracker(status)
        self.exporter = PlotExporter(self.busy, dialog_parent, self)
        self.exporter.finished.connect(self.export_finished)
        self.exporter.message.connect(self.message)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(RENDER_DEBOUNCE_MS)
        self._render_timer.timeout.connect(self._render_current)

        service.detected.connect(self._on_detected)
        workspace.current_changed.connect(self._on_tab_changed)
        workspace.tab_closing.connect(self._on_tab_closing)
        params.changed.connect(self._on_param_changed)
        params.export_requested.connect(self.export)
        params.remap_requested.connect(self.remap)
        params.restore_requested.connect(self.restore_defaults)
        settings.warning.connect(self._on_settings_warning)

    # -- queries --------------------------------------------------------------------------------
    def current_plot(self) -> PlotView | None:
        widget = self.workspace.current()
        return widget if isinstance(widget, PlotView) else None

    def plot_of(self, folder: Path) -> PlotView | None:
        """The open plot of ``folder``: the current tab first. A figure of several folders (bands
        + DOS) is not the plot of its first one."""

        def shows(view: PlotView) -> bool:
            return view.session.folder == folder and not view.session.composite

        view = self.current_plot()
        if view is not None and shows(view):
            return view
        views = (w for _key, w in self.workspace.items() if isinstance(w, PlotView))
        return next((w for w in views if shows(w)), None)

    # -- entry points ---------------------------------------------------------------------------
    def generate(self, folder: Path, auto_export: bool = True) -> None:
        """Detect → (choose / map manually) → load in a worker → plot tab → save to plots/.

        Detection runs in the service pool (big outputs, network disks): the rest continues
        in ``_on_detected``.
        """
        key = str(folder)
        if key in self._detecting:
            return
        self._detecting[key] = auto_export
        self.busy.begin(f"detect:{key}", "Detectando cálculo…")
        self.service.request(Path(folder), fresh=True)

    def preview(self, folder: Path) -> None:
        """Plot ``folder`` in the workspace without saving it; an open plot of that folder is
        only brought to front, keeping its edits."""
        self.panel_requested.emit("workspace")
        self.panel_requested.emit("params")
        view = self.plot_of(folder)
        if view is not None:
            self.workspace.set_current(view)
        else:
            self.generate(folder, auto_export=False)

    def plot_file(self, path: Path, kind: str) -> None:
        """Preview the plot of one output file (context-menu "Plotar", "Plotar SCF" button).

        Not saved to plots/: "Salvar em plots/" / Ctrl+E does that, as for the "Plot" button.
        """
        module = module_for(kind)
        assert module.single_file_role is not None
        mapping = {module.single_file_role: [path]}
        self._load(
            ManualTarget(module, path.parent, mapping, self.service.sniff_cache.sniff), False
        )

    def plot_pair(self, bands: Path, dos: Path) -> None:
        """ "Bandas com DOS" (spec 22): both folders are detected and paired in the load worker.
        Not saved to plots/; an open figure of the same pair is replaced, keeping its edits."""
        sniff = self.service.sniff_cache.sniff
        self._load(PairTarget(bands, dos, sniff, self.memory), auto_export=False)

    def plot_open_file(self) -> None:
        if self._plot_file_source is not None:
            self.plot_file(*self._plot_file_source)

    def remap(self) -> None:
        view = self.current_plot()
        if view is None:
            return
        results = [view.session.result]
        target = self._map_manually(view.session.folder, results, mapping_message(results))
        if target is not None:
            self._load(target, auto_export=False)

    def export(self) -> bool:
        """Save the current plot to <folder>/plots/ (PRD §4.4); whether an export started."""
        view = self.current_plot()
        if view is None:
            self.message.emit("Nenhum gráfico aberto.", "warning", 3000)
            return False
        return self.exporter.export(view.session)

    @property
    def exporting(self) -> bool:
        return self.exporter.running

    def wait_for_exports(self) -> bool:
        """Before a rename moves a folder: an export must not recreate the old one."""
        return self.exporter.wait()

    def cancel_loads(self) -> None:
        """Window close: the datasets being loaded are not wanted any more."""
        self._loads.cancel_all()

    def shutdown(self, timeout_ms: int = EXPORT_WAIT_MS) -> bool:
        """Window close: loads are dropped, exports finish (no half-written files)."""
        self.cancel_loads()
        return self.exporter.shutdown(timeout_ms)

    # -- detection → choice -----------------------------------------------------------------------
    def _on_detected(self, key: str) -> None:
        self.update_plot_file_button()
        if key not in self._detecting:
            return
        # Taken now: by the next loop turn a refresh or sync may have invalidated the cache.
        results = self.service.results(Path(key))
        if results is None:
            return  # invalidated already: detection runs again and lands here
        auto_export = self._detecting.pop(key)
        self.busy.end(f"detect:{key}")
        # Not a worker: the dialogs below must not open inside the detection signal's slot.
        QTimer.singleShot(0, partial(self._plot_detected, Path(key), results, auto_export))

    def _plot_detected(
        self, folder: Path, results: list[DetectionResult], auto_export: bool
    ) -> None:
        choice = plot_choice(results)
        if isinstance(choice, Ambiguous):
            target = choose_result(self._dialog_parent, choice.results)
        elif isinstance(choice, Chosen):
            target = choice.result
        else:
            target = self._map_manually(folder, results, choice.message)
        if target is not None:
            self._load(target, auto_export)

    def _map_manually(
        self, folder: Path, results: list[DetectionResult], message: str
    ) -> ManualTarget | None:
        modules = plottable_modules()
        answer = ask_mapping(self._dialog_parent, folder, modules, results, message)
        if answer is None:
            return None
        kind, mapping, remember = answer
        module = next(m for m in modules if m.kind == kind)
        if remember:
            self.memory.set_mapping(folder, kind, mapping)
            self.service.invalidate(folder)
        return ManualTarget(module, folder, mapping, self.service.sniff_cache.sniff)

    # -- loading ------------------------------------------------------------------------------------
    def _load(self, target: DetectionResult | ManualTarget | PairTarget, auto_export: bool) -> None:
        key = target_key(target)
        if key in self._loading:
            return
        self.settings.flush(key)  # queued before the read of this plot's .plot
        self._loading[key] = _Loading(auto_export)
        self.busy.begin(f"load:{key}", f"Carregando {target.module.display_name.lower()}…")
        self.workspace.set_busy(key, True)  # an open tab of this plot, until it is replaced
        sniff = self.service.sniff_cache.sniff
        self._loads.submit(
            key, load_plot, target, sniff, on_done=self._on_data, on_error=self._on_load_failed
        )

    def _on_data(self, key: str, loaded: tuple[DetectionResult, Any]) -> None:
        loading = self._loading.get(key)
        if loading is None:
            return
        loading.result, loading.dataset = loaded
        result = loading.result
        self.settings.read(
            key, result.folder, result.kind, on_done=self._on_stored, on_error=self._on_load_failed
        )

    def _on_stored(self, key: str, stored: tuple[dict[str, Any] | None, list[str]]) -> None:
        loading = self._finish_load(key)
        if loading is not None and loading.result is not None:
            self.show_loaded(loading.result, loading.dataset, stored, loading.auto_export)

    def _on_load_failed(self, key: str, error: Exception) -> None:
        if self._finish_load(key) is None:
            return
        if isinstance(error, LoadError):
            text = str(error)
        else:  # parsing errors must reach the user, not kill the worker
            log.error("load failed", exc_info=error)
            text = f"{type(error).__name__}: {error}"
        self.message.emit("Falha ao carregar os dados do gráfico.", "error", 8000)
        QMessageBox.warning(self._dialog_parent, "Não foi possível gerar o gráfico", text)
        self.plot_failed.emit(text)

    def _finish_load(self, key: str) -> _Loading | None:
        self.busy.end(f"load:{key}")
        self.workspace.set_busy(key, False)
        return self._loading.pop(key, None)

    def show_loaded(
        self,
        result: DetectionResult,
        dataset: Any,
        stored: tuple[dict[str, Any] | None, list[str]],
        auto_export: bool = False,
    ) -> PlotSession:
        """The plot tab of a loaded result (replacing an open one of the same plot)."""
        existing = self.workspace.widget_for(target_key(result))
        open_session = existing.session if isinstance(existing, PlotView) else None
        session, warnings = build_session(
            result, dataset, self._config(), stored, self.memory, open_session, self.stores
        )
        return self.show_session(session, warnings, auto_export)

    def show_session(
        self, session: PlotSession, warnings: list[str] | None = None, auto_export: bool = False
    ) -> PlotSession:
        """The tab of ``session`` (a loaded plot, a grid), replacing an open one with its key."""
        warnings = list(warnings or []) + self.stores.pop_warnings()
        if self.workspace.widget_for(session.key) is not None:
            self._replacing = session.key  # the new tab shows this dataset: it stays cached
            try:
                self.workspace.close_key(session.key)
            finally:
                self._replacing = None
        view = PlotView(self.theme, session)
        view.rendered.connect(self._on_rendered)
        view.limits_changed.connect(self._on_limits_changed)
        view.export_requested.connect(self.export)
        self.workspace.add(
            session.key, view, session.title, ("bubble_chart", "accent"), str(session.plot_target)
        )
        self.panel_requested.emit("workspace")  # workspace.add made the tab current: bound
        self.panel_requested.emit("params")
        self.message.emit(
            f"{session.module.display_name}: {session.plot_target.name}", "info", 4000
        )
        if warnings:
            self.message.emit(warnings[0], "warning", 8000)
        if auto_export:
            self.export()
        self.plot_ready.emit(session)
        return session

    # -- open plots ---------------------------------------------------------------------------------
    def _on_tab_changed(self, widget) -> None:
        if isinstance(widget, PlotView):
            self.params.bind(widget.session)
        elif widget is None:
            self.params.bind(None)
        self.update_readout()
        self.update_plot_file_button()

    def _on_tab_closing(self, widget) -> None:
        if isinstance(widget, PlotView):
            key = widget.session.key
            self.settings.flush(key)
            self.params.discard(key)
            # Closing the tab ends a load of it still pending (a regenerate): nothing opens later.
            self._loads.cancel(key)
            self._finish_load(key)
            if key != self._replacing:  # big datasets go with their tab (spec 27-4 R2.4)
                for path in widget.session.paths:
                    drop_cached(path, min_bytes=CLOSE_DROP_MIN_BYTES)

    def _on_param_changed(self, name: str) -> None:
        self._render_timer.start()
        session = self.params.session
        # What a user store keeps (the atoms of a compound) is saved there, not in the .plot.
        if session is not None and not session.persist(name, self.stores):
            self.settings.mark(session)

    def _on_limits_changed(self) -> None:
        # Pan/zoom or Reset in the plot toolbar (always the visible, current plot).
        self.params.refresh_values()
        view = self.current_plot()
        if view is not None:
            self.settings.mark(view.session)

    def restore_defaults(self) -> None:
        session = self.params.session
        if session is None:
            return
        name = f"{session.kind}.plot"
        answer = QMessageBox.question(
            self._dialog_parent,
            "Restaurar padrões",
            f"Voltar todos os ajustes deste gráfico ao padrão e apagar {name}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        session.params = copy.deepcopy(session.defaults)
        self.settings.delete(session)
        self.params.bind(session)
        view = self.workspace.widget_for(session.key)
        if isinstance(view, PlotView):
            view.render()

    def _render_current(self) -> None:
        view = self.current_plot()
        if view is not None:
            view.render()

    def _on_rendered(self, _info) -> None:
        # Any open plot re-renders on a theme change: show what the current one says.
        self.update_readout()
        view = self.current_plot()
        if view is not None and view.session is self.params.session and view.session.info:
            self.params.update_readout()

    def update_readout(self) -> None:
        """Footer summary of the plot on screen, empty when none is (spec 1 R6)."""
        view = None if self.workspace.isHidden() else self.current_plot()
        info = view.session.info if view is not None else None
        if view is None or info is None:
            self.status.set_readout("")
            return
        params = view.session.params
        dpi = params.export_dpi
        px = f"{round(params.figure_width * dpi)}×{round(params.figure_height * dpi)} px"
        name = view.session.plot_target.name
        self.status.set_readout(f"{name} · {info.summary} · {px} ({dpi} DPI)")

    def update_plot_file_button(self) -> None:
        """ "Plotar SCF" while the current tab is an output one module can plot alone."""
        widget = self.workspace.current()
        source = None
        if isinstance(widget, TextViewer):
            sniff = self.service.file_sniff(widget.path)
            if sniff is None:  # not detected yet: the button follows when it arrives
                self.service.results(widget.path.parent)
            if module := module_for_file(sniff):
                source = (widget.path, module.kind)
        self._plot_file_source = source
        self.plot_file_available.emit(source is not None)

    def _on_settings_warning(self, text: str) -> None:
        self.message.emit(text, "warning", 8000)
