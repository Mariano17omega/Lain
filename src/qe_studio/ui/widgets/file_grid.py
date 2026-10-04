"""File view of the active simulation: cards (grid) or rows (list) (PRD §2.1.3)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtGui import QActionGroup, QFont, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ...core.file_kinds import human_size, status_label
from ...core.paths import count_entries
from ...core.tasks import TaskGroup
from ..file_types import file_visual, level_token
from ..painting import mono_font
from ..services import DetectionService
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader, selection_of, viewport_of
from .fs_model import SORT_DATE, SORT_NAME, SORT_SIZE, FileFilterProxy, make_fs_model

CARD = QSize(148, 86)
ROW = 26


class FileCardDelegate(QStyledItemDelegate):
    def __init__(self, panel: FilePanel):
        super().__init__()
        self.panel = panel

    @property
    def theme(self) -> ThemeManager:
        return self.panel.theme

    def sizeHint(self, option, index) -> QSize:
        if self.panel.grid_mode:
            return CARD - QSize(6, 6)
        return QSize(option.rect.width(), ROW)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        proxy = self.panel.proxy
        path = proxy.path(index)
        is_dir = proxy.is_dir(index)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        theme = self.theme
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2.5, 2.5, -2.5, -2.5)
        if selected:
            background, border = theme.color("accent_soft"), theme.color("accent")
        elif hovered:
            background, border = theme.color("card_hover"), theme.color("border_strong")
        else:
            background, border = theme.color("card"), theme.color("border")
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 4, 4)

        if proxy.is_up(index):  # the "folder above" shortcut (spec 5 R2)
            title = ".."
            icon_name, token = "drive_folder_upload", "icon_folder"
            meta, meta_token = "pasta acima", "text_dim"
        else:
            title = path.name
            icon_name, token = file_visual(path, is_dir)
            meta, meta_token = self._meta(path, is_dir, proxy.fs.size(proxy.mapToSource(index)))
        name_color = theme.color("accent_text" if selected or is_dir else "text")
        name_font = mono_font(12, QFont.Weight.Bold if selected else QFont.Weight.Normal)
        if self.panel.grid_mode:
            tile = QRectF(rect.center().x() - 17, rect.top() + 7, 34, 34)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("window"))
            painter.drawRoundedRect(tile, 4, 4)
            painter.drawPixmap(
                int(tile.center().x() - 10),
                int(tile.center().y() - 10),
                theme.pixmap(icon_name, token, 20),
            )
            painter.setFont(name_font)
            painter.setPen(name_color)
            name_rect = QRect(
                int(rect.left()) + 6, int(tile.bottom()) + 4, int(rect.width()) - 12, 16
            )
            name = painter.fontMetrics().elidedText(
                title, Qt.TextElideMode.ElideMiddle, name_rect.width()
            )
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, name)
            painter.setFont(mono_font(10))
            painter.setPen(theme.color(meta_token))
            painter.drawText(
                QRect(int(rect.left()), name_rect.bottom() + 1, int(rect.width()), 14),
                Qt.AlignmentFlag.AlignCenter,
                meta,
            )
        else:
            painter.drawPixmap(
                int(rect.left()) + 6, int(rect.center().y() - 8), theme.pixmap(icon_name, token, 16)
            )
            painter.setFont(mono_font(10))
            meta_width = painter.fontMetrics().horizontalAdvance(meta) + 8
            painter.setPen(theme.color(meta_token))
            painter.drawText(
                rect.toRect().adjusted(0, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                meta,
            )
            painter.setFont(name_font)
            painter.setPen(name_color)
            name_rect = rect.toRect().adjusted(28, 0, -meta_width - 8, 0)
            name = painter.fontMetrics().elidedText(
                title, Qt.TextElideMode.ElideMiddle, name_rect.width()
            )
            painter.drawText(
                name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name
            )
        painter.restore()

    def _meta(self, path: Path, is_dir: bool, size: int) -> tuple[str, str]:
        """Folders: entry count. Files: state only on cards, size (and state) in list mode."""
        if is_dir:
            count = self.panel.item_count(path)
            return (f"{count} itens" if count is not None else "pasta"), "text_dim"
        label = status_label(path, size, self.panel.service.file_sniff(path))
        if label is None:
            return ("", "text_dim") if self.panel.grid_mode else (human_size(size), "text_dim")
        text, token = label[0], level_token(label[1])
        return (text, token) if self.panel.grid_mode else (f"{human_size(size)} · {text}", token)


class FilePanel(QWidget):
    file_activated = pyqtSignal(Path)
    folder_activated = pyqtSignal(Path)
    file_selected = pyqtSignal(Path)
    item_menu_requested = pyqtSignal(Path, QPoint)  # item, global position

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

        self.model = make_fs_model(root, self, dot_dot=True)
        self.proxy = FileFilterProxy(hidden_dirs, parent=self)
        self.proxy.setSourceModel(self.model)
        self.proxy.set_root(Path(root))
        self.view = QListView()
        self.view.setObjectName("fileGrid")
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(FileCardDelegate(self))
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QListView.SelectionMode.SingleSelection)
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
        self._pending_select: Path | None = None  # a file to select once its folder is listed
        self.model.directoryLoaded.connect(self._update_count)
        self.model.directoryLoaded.connect(self._select_pending)
        self.proxy.rowsInserted.connect(self._update_count)
        self.proxy.rowsInserted.connect(self._select_pending)
        self.proxy.rowsRemoved.connect(self._update_count)
        service.detected.connect(self._on_detected)
        theme.theme_changed.connect(self._on_theme_changed)
        self.set_folder(root)

    @property
    def folder(self) -> Path:
        return self._folder

    def set_folder(self, folder: Path) -> None:
        self._folder = Path(folder)
        if self._pending_select is not None and self._pending_select.parent != self._folder:
            self._pending_select = None
        self._clear_counts()
        self.model.setRootPath(str(folder))
        self.view.setRootIndex(self.proxy.index_for(folder))
        self.service.results(self._folder)  # warm the sniff cache for status labels
        self._update_count()

    def apply_config(self, root: Path, hidden_dirs: list[str]) -> None:
        """A reloaded config: project root and hidden folders; shows the root."""
        self.proxy.set_hidden_dirs(hidden_dirs)
        self.proxy.set_root(root)
        self.set_folder(root)

    def refresh(self) -> None:
        self._clear_counts()
        viewport_of(self.view).update()

    def shutdown(self, msecs: int = 1000) -> bool:
        """Drop queued counts and wait for the running ones (window close): the pool's
        destructor would otherwise run every queued scan, without a time limit."""
        return self._count_tasks.shutdown(msecs)

    def _on_theme_changed(self, _name: str) -> None:
        viewport_of(self.view).update()

    def _on_detected(self, _folder: str) -> None:
        viewport_of(self.view).update()  # status labels from the new sniffs

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
            view.setGridSize(CARD)
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

    def go_up(self) -> None:
        """Folder above, never leaving the project root."""
        if self.proxy.root is not None and self._folder != self.proxy.root:
            self.folder_activated.emit(self._folder.parent)

    def _update_count(self, *_args) -> None:
        root = self.view.rootIndex()
        rows = self.proxy.rowCount(root)
        if rows and self.proxy.is_up(self.proxy.index(0, 0, root)):
            rows -= 1  # ".." is a shortcut, not an entry
        self.header.count.setText(f"({rows})")

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

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.view.indexAt(pos)
        if index.isValid() and not self.proxy.is_up(index):
            self.item_menu_requested.emit(
                self.proxy.path(index), viewport_of(self.view).mapToGlobal(pos)
            )
