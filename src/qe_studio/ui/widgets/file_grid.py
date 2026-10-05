"""File view of the active simulation: cards (grid) or rows (list) (PRD §2.1.3)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QSize,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtGui import QActionGroup, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QListView,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ...core.filtering import BADGES, NO_BADGE, NO_STATE, STATES, VISUALS
from ...core.paths import count_entries
from ...core.tasks import TaskGroup
from ..services import DetectionService
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader, selection_of, viewport_of
from .file_card import FileCardDelegate, card_size
from .filter_bar import FilterBar
from .fs_model import SORT_DATE, SORT_NAME, SORT_SIZE, FileFilterProxy, make_fs_model
from .grid_view import GridView


class FilePanel(QWidget):
    file_activated = pyqtSignal(Path)
    folder_activated = pyqtSignal(Path)
    file_selected = pyqtSignal(Path)
    files_activated = pyqtSignal(list)  # Enter with several items selected: list[Path]
    selection_changed = pyqtSignal(list)  # list[Path], without ".."
    item_menu_requested = pyqtSignal(list, QPoint)  # list[Path] (the selection), global position

    def __init__(
        self,
        theme: ThemeManager,
        service: DetectionService,
        root: Path,
        hidden_dirs: list[str],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.theme, self.service = theme, service
        self.setObjectName("filePanel")
        self.grid_mode = True
        self._counts: dict[str, int | None] = {}
        self._count_pool = QThreadPool()  # no Qt parent: see core/tasks.py, "private pools"
        self._count_pool.setMaxThreadCount(2)
        # Subfolder entry counts, off the GUI thread (big folders, slow network mounts); a
        # refresh cancels them all, so counts read before it are dropped.
        self._count_tasks = TaskGroup(self._count_pool)
        self._folder = Path(root)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = PanelHeader(theme, "Arquivos", "grid_view")
        self.grid_button = self.header.add_button(IconButton(theme, "grid_view", "Grade"))
        self.list_button = self.header.add_button(IconButton(theme, "view_list", "Lista"))
        for button in (self.grid_button, self.list_button):
            button.setCheckable(True)
        self.grid_button.setChecked(True)
        self.sort_button = self.header.add_button(IconButton(theme, "sort", "Ordenar"))
        self.sort_button.setPopupMode(IconButton.ToolButtonPopupMode.InstantPopup)
        self.sort_button.setMenu(self._sort_menu())
        layout.addWidget(self.header)
        self.filter_bar = FilterBar(
            "Filtrar por nome (* e ?)",
            [
                ("badges", "Pastas", [*BADGES, NO_BADGE]),
                ("states", "Estado do arquivo", [*STATES, NO_STATE]),
                ("visuals", "Tipo do arquivo", VISUALS),
            ],
        )
        layout.addWidget(self.filter_bar)

        self.model = make_fs_model(root, self, dot_dot=True)
        self.proxy = FileFilterProxy(hidden_dirs, parent=self, service=service)
        self.proxy.setSourceModel(self.model)
        self.proxy.set_root(Path(root))
        self.view = GridView()
        self.view.setObjectName("fileGrid")
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(FileCardDelegate(self))
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.proxy.sort(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.view, 1)
        self._apply_mode()

        self.grid_button.clicked.connect(lambda: self.set_grid_mode(True))
        self.list_button.clicked.connect(lambda: self.set_grid_mode(False))
        self.view.activated.connect(self._on_activated)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        for keys in ("Backspace", "Alt+Up"):
            shortcut = QShortcut(QKeySequence(keys), self.view)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self.go_up)
        selection_of(self.view).currentChanged.connect(self._on_current)
        selection_of(self.view).selectionChanged.connect(self._on_selection_changed)
        self.view.enter_many.connect(self._on_enter_many)
        self.filter_bar.changed.connect(self._on_filter_changed)
        self.filter_bar.closed.connect(self.view.setFocus)
        self.filter_bar.accepted.connect(self.view.setFocus)
        find = QShortcut(QKeySequence("Ctrl+F"), self)  # with the focus in this panel only
        find.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find.activated.connect(self.filter_bar.open)
        self._fixing_selection = False
        self._pending_select: Path | None = None  # a file to select once its folder is listed
        self.model.directoryLoaded.connect(self._update_count)
        self.model.directoryLoaded.connect(self._select_pending)
        self.proxy.rowsInserted.connect(self._update_count)
        self.proxy.rowsInserted.connect(self._select_pending)
        self.proxy.rowsRemoved.connect(self._update_count)
        service.detected.connect(self._on_detected)
        theme.theme_changed.connect(self._on_theme_changed)
        theme.scale_changed.connect(self._on_scale_changed)
        self.set_folder(root)

    @property
    def folder(self) -> Path:
        return self._folder

    def set_folder(self, folder: Path) -> None:
        self._folder = Path(folder)
        if self._pending_select is not None and self._pending_select.parent != self._folder:
            self._pending_select = None
        self._clear_counts()
        if self.filter_bar.is_active or not self.filter_bar.isHidden():
            self.filter_bar.dismiss()  # a filter is for the folder it was typed in
        self.proxy.set_scope(self._folder)
        self.model.setRootPath(str(folder))
        self.view.setRootIndex(self.proxy.index_for(folder))
        self.service.results(self._folder)  # warm the sniff cache for status labels
        self._update_count()

    def set_view_root(self, folder: Path) -> None:
        """The top the grid may go up to (spec 31: the selected project, else the root): there
        is no ``..`` row in it and ``go_up`` stops. The folder shown changes with the tree's."""
        self.proxy.set_root(folder)

    def apply_config(self, root: Path, hidden_dirs: list[str]) -> None:
        """A reloaded config: project root and hidden folders; shows the root."""
        self.proxy.set_hidden_dirs(hidden_dirs)
        self.proxy.set_root(root)
        self.set_folder(root)

    def refresh(self) -> None:
        self._clear_counts()
        viewport_of(self.view).update()

    def shutdown(self, msecs: int = 1000) -> bool:
        """Window close: the model stops talking to the proxy and this panel (see
        ``FileFilterProxy.detach``); queued counts are dropped and the running ones waited for,
        or the pool's destructor would run every queued scan, without a time limit."""
        self.model.blockSignals(True)
        self.proxy.detach()
        return self._count_tasks.shutdown(msecs)

    def _on_theme_changed(self, _name: str) -> None:
        viewport_of(self.view).update()

    def _on_scale_changed(self, _scale: float) -> None:
        self._apply_mode()  # cards and rows are taller or shorter now

    def _on_detected(self, _folder: str) -> None:
        viewport_of(self.view).update()  # status labels from the new sniffs
        self.proxy.refilter_later()  # a badge or a state may now match

    def set_grid_mode(self, grid: bool) -> None:
        self.grid_mode = grid
        self.grid_button.setChecked(grid)
        self.list_button.setChecked(not grid)
        self._apply_mode()

    def select_file(self, path: Path) -> None:
        index = self.proxy.index_for(path)
        if index.isValid():
            self._pending_select = None
            self.view.setCurrentIndex(index)
        else:
            self._pending_select = Path(path)  # the model is still reading the folder

    def _select_pending(self, *_args) -> None:
        if self._pending_select is not None:
            self.select_file(self._pending_select)

    def item_count(self, folder: Path) -> int | None:
        """Cached entry count (None while counting in the pool, or if unreadable)."""
        key = str(folder)
        if key in self._counts:
            return self._counts[key]
        if self._count_tasks.active(key) is None:
            self._count_tasks.submit(key, count_entries, key, on_done=self._on_counted)
        return None

    def _clear_counts(self) -> None:
        self._count_tasks.cancel_all()
        self._counts.clear()

    def _on_counted(self, key: str, count: int | None) -> None:
        self._counts[key] = count
        viewport_of(self.view).update()

    def _apply_mode(self) -> None:
        view = self.view
        if self.grid_mode:
            view.setViewMode(QListView.ViewMode.IconMode)
            view.setGridSize(card_size())
            view.setWrapping(True)
            view.setResizeMode(QListView.ResizeMode.Adjust)
            view.setMovement(QListView.Movement.Static)
            view.setSpacing(0)
        else:
            view.setViewMode(QListView.ViewMode.ListMode)
            view.setGridSize(QSize())
            view.setWrapping(False)
            view.setSpacing(0)
        view.doItemsLayout()  # pyright: ignore[reportAttributeAccessIssue]  (public Qt slot, not in the stubs)

    def _sort_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        self._sort_actions = {}
        for label, column in (("Nome", SORT_NAME), ("Tamanho", SORT_SIZE), ("Data", SORT_DATE)):
            action = menu.addAction(label)
            assert action is not None
            action.setCheckable(True)
            action.setChecked(column == SORT_NAME)
            group.addAction(action)
            action.triggered.connect(lambda _c=False, col=column: self.set_sort(col))
            self._sort_actions[column] = action
        return menu

    @property
    def sort_column(self) -> int:
        return self.proxy.sort_column

    def set_sort(self, column: int) -> None:
        """Sort by name (A→Z), size or date (largest/newest first)."""
        self._sort_actions[column].setChecked(True)
        self.proxy.sort_column = column
        self.proxy.invalidate()
        order = Qt.SortOrder.AscendingOrder if column == SORT_NAME else Qt.SortOrder.DescendingOrder
        self.proxy.sort(0, order)

    @staticmethod
    def shortcut_help() -> list[tuple[str, str, str]]:
        """(action, keys, where) of the keys this panel handles itself (not menu actions)."""
        return [
            ("Subir uma pasta", "Backspace", "Grade de arquivos"),
            ("Subir uma pasta", "Alt+↑", "Grade de arquivos"),
            ("Filtrar a grade", "Ctrl+F", "Grade de arquivos"),
            ("Abrir os arquivos selecionados", "Enter", "Grade de arquivos"),
        ]

    def go_up(self) -> None:
        """Folder above, never leaving the project root."""
        if self.proxy.root is not None and self._folder != self.proxy.root:
            self.folder_activated.emit(self._folder.parent)

    def _update_count(self, *_args) -> None:
        root = self.view.rootIndex()
        rows = self.proxy.rowCount(root)
        if rows and self.proxy.is_up(self.proxy.index(0, 0, root)):
            rows -= 1  # ".." is a shortcut, not an entry
        if self.proxy.filtering:
            self.header.count.setText(f"({rows} de {self.proxy.unfiltered_count(root)})")
        else:
            self.header.count.setText(f"({rows})")

    def _on_filter_changed(self) -> None:
        bar = self.filter_bar
        category = bar.category_filter()
        self.proxy.set_filters(bar.name_text(), category)
        self._update_count()
        if category.badges:
            self._request_pending_badges()

    def _request_pending_badges(self) -> None:
        """A badge filter needs the detection of the folders listed now: ask for it (the grid
        paints no badges, so nothing else would). The filter itself reads the cache only."""
        root = self.view.rootIndex()
        for row in range(self.proxy.rowCount(root)):
            index = self.proxy.index(row, 0, root)
            if self.proxy.is_pending(index):
                self.service.request(self.proxy.path(index))

    def _on_activated(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        path = self.proxy.path(index)
        if self.proxy.is_dir(index):
            self.folder_activated.emit(path)
        else:
            self.file_activated.emit(path)

    def _on_current(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if current.isValid() and not self.proxy.is_dir(current):
            self.file_selected.emit(self.proxy.path(current))

    # -- selection (spec 16 R5) ---------------------------------------------------------------
    def selected_paths(self) -> list[Path]:
        """The selected items in view order; ".." never counts."""
        indexes = [i for i in selection_of(self.view).selectedIndexes() if i.column() == 0]
        indexes.sort(key=lambda i: i.row())
        return [self.proxy.path(i) for i in indexes if not self.proxy.is_up(i)]

    def _on_selection_changed(self, *_args) -> None:
        if self._fixing_selection:
            return
        selection = selection_of(self.view)
        up = [i for i in selection.selectedIndexes() if self.proxy.is_up(i)]
        if up:  # "..": Ctrl+A, Shift+click or a rubber band reached it
            self._fixing_selection = True
            try:
                for index in up:
                    selection.select(index, QItemSelectionModel.SelectionFlag.Deselect)
            finally:
                self._fixing_selection = False
        self.selection_changed.emit(self.selected_paths())

    def _on_enter_many(self) -> None:
        self.files_activated.emit(self.selected_paths())

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid() or self.proxy.is_up(index):
            return
        selection = selection_of(self.view)
        if not selection.isSelected(index):  # outside the selection: it becomes the selection
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.item_menu_requested.emit(
            self.selected_paths(), viewport_of(self.view).mapToGlobal(pos)
        )
