"""Folder explorer: project tree with calculation badges (PRD §2.1.2 navigation mode)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ...core.file_kinds import human_size, status_label
from ...core.filtering import BADGES, NO_BADGE
from ..file_types import file_visual, level_token
from ..painting import mono_font, paint_badge, ui_font
from ..services import DetectionService
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader, selection_of, viewport_of
from .filter_bar import FilterBar
from .fs_model import FileFilterProxy, make_fs_model
from .nav_sections import NavSection

ROW_HEIGHT = 22


class ExplorerDelegate(QStyledItemDelegate):
    def __init__(self, theme: ThemeManager, service: DetectionService, proxy: FileFilterProxy):
        super().__init__()
        self.theme, self.service, self.proxy = theme, service, proxy

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = type(opt.icon)()
        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        path = self.proxy.path(index)
        is_dir = self.proxy.is_dir(index)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect
        painter.save()
        icon_name, token = file_visual(path, is_dir)
        if is_dir and option.state & QStyle.StateFlag.State_Open:
            icon_name = "folder_open"
        pixmap = self.theme.pixmap(icon_name, token, 16)
        painter.drawPixmap(rect.left() + 2, rect.top() + (rect.height() - 16) // 2, pixmap)

        right = rect.right() - 6
        center = rect.center().y() + 0.5
        if is_dir:
            for result in reversed(self.service.results(path) or []):
                left = paint_badge(
                    painter, right, center, result.badge, self.theme, result.badge_token
                )
                right = left - 4
            if self.proxy.is_pending(index):  # a badge filter waits for this folder's detection
                right = self._paint_pending(painter, right, rect)
        else:
            size = self.proxy.fs.size(self.proxy.mapToSource(index))
            right = self._paint_file_meta(painter, path, size, right, rect)

        painter.setFont(
            ui_font(12, QFont.Weight.Medium if selected and is_dir else QFont.Weight.Normal)
        )
        painter.setPen(self.theme.color("accent_text" if selected else "text"))
        text_rect = QRect(
            rect.left() + 24, rect.top(), int(right) - rect.left() - 28, rect.height()
        )
        name = painter.fontMetrics().elidedText(
            path.name, Qt.TextElideMode.ElideMiddle, max(text_rect.width(), 0)
        )
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name
        )
        painter.restore()

    def _paint_pending(self, painter: QPainter, right: float, rect: QRect) -> float:
        painter.setFont(mono_font(10))
        text = "detectando…"
        width = painter.fontMetrics().horizontalAdvance(text)
        painter.setPen(self.theme.color("text_dim"))
        painter.drawText(
            QRect(int(right - width), rect.top(), width + 1, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            text,
        )
        return right - width - 6

    def _paint_file_meta(
        self, painter: QPainter, path: Path, size: int, right: float, rect: QRect
    ) -> float:
        painter.setFont(mono_font(10))
        label = status_label(path, size, self.service.file_sniff(path))
        text, token = (label[0], level_token(label[1])) if label else (human_size(size), "text_dim")
        width = painter.fontMetrics().horizontalAdvance(text)
        painter.setPen(self.theme.color(token))
        painter.drawText(
            QRect(int(right - width), rect.top(), width + 1, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            text,
        )
        return right - width - 6


class ExplorerPanel(QWidget):
    folder_selected = pyqtSignal(Path)
    file_selected = pyqtSignal(Path)
    file_activated = pyqtSignal(Path)
    item_menu_requested = pyqtSignal(list, QPoint)  # [item], global position

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
        self.setObjectName("explorerPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PanelHeader(theme, "Explorador", "folder_open")
        self.collapse_button = header.add_button(IconButton(theme, "unfold_less", "Recolher tudo"))
        self.refresh_button = header.add_button(IconButton(theme, "refresh", "Atualizar (F5)"))
        layout.addWidget(header)
        # Favorite and recent folders (spec 16 R4): hidden while empty, filled by the window's
        # NavigationController, which also answers their clicks.
        self.favorites = NavSection(theme, "Favoritos", "star", "accent")
        self.recents = NavSection(theme, "Recentes", "history", "text_muted")
        for section in (self.favorites, self.recents):
            layout.addWidget(section)
            section.menu_requested.connect(self.item_menu_requested)
        # Only the folders the model has loaded (the ones opened so far) can be filtered.
        self.filter_bar = FilterBar(
            "Filtrar por nome (pastas já abertas)", [("badges", "Pastas", [*BADGES, NO_BADGE])]
        )
        layout.addWidget(self.filter_bar)

        self.model = make_fs_model(root, self)
        self.proxy = FileFilterProxy(hidden_dirs, parent=self, service=service, keep_ancestors=True)
        self.proxy.setSourceModel(self.model)
        self.tree = QTreeView()
        self.tree.setObjectName("explorerTree")
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setItemDelegate(ExplorerDelegate(theme, service, self.proxy))
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.tree, 1)

        self.set_root(root)
        selection_of(self.tree).currentChanged.connect(self._on_current)
        self.tree.activated.connect(self._on_activated)  # double click or Enter
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.collapse_button.clicked.connect(self.tree.collapseAll)
        self.refresh_button.clicked.connect(self.refresh)
        self.filter_bar.changed.connect(self._on_filter_changed)
        self.filter_bar.closed.connect(self.tree.setFocus)
        self.filter_bar.accepted.connect(self.tree.setFocus)
        find = QShortcut(QKeySequence("Ctrl+F"), self)  # with the focus in this panel only
        find.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find.activated.connect(self.filter_bar.open)
        service.detected.connect(self._on_detected)
        theme.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str) -> None:
        viewport_of(self.tree).update()

    def _on_detected(self, _folder: str) -> None:
        viewport_of(self.tree).update()
        self.proxy.refilter_later()  # a badge may now match

    def _on_filter_changed(self) -> None:
        bar = self.filter_bar
        self.proxy.set_filters(bar.name_text(), bar.category_filter())

    @property
    def root(self) -> Path:
        return self._root

    def set_root(self, root: Path) -> None:
        self._root = Path(root)
        self.proxy.set_root(self._root)
        self.model.setRootPath(str(root))
        self.tree.setRootIndex(self.proxy.index_for(root))

    def apply_config(self, root: Path, hidden_dirs: list[str]) -> None:
        """A reloaded config: project root and hidden folders."""
        self.proxy.set_hidden_dirs(hidden_dirs)
        self.set_root(root)

    def refresh(self) -> None:
        """Repaint the badges; the caller invalidates the detection it knows is stale."""
        viewport_of(self.tree).update()

    def current_path(self) -> Path | None:
        index = self.tree.currentIndex()
        return self.proxy.path(index) if index.isValid() else None

    def current_folder(self) -> Path:
        path = self.current_path()
        if path is None:
            return self._root
        return path if path.is_dir() else path.parent

    def select_path(self, path: Path) -> None:
        if Path(path) == self._root:
            # The root is the tree's root index, not a row: nothing to highlight.
            self.tree.setCurrentIndex(QModelIndex())
            self.folder_selected.emit(self._root)
            return
        index = self.proxy.index_for(path)
        if not index.isValid() and self.filter_bar.is_active:
            self.filter_bar.dismiss()  # the filter hides it: navigation wins
            index = self.proxy.index_for(path)
        if index.isValid():
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)
            self.tree.expand(index)

    def _on_current(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        path = self.proxy.path(current)
        if self.proxy.is_dir(current):
            self.folder_selected.emit(path)
        else:
            self.folder_selected.emit(path.parent)
            self.file_selected.emit(path)

    def _on_activated(self, index: QModelIndex) -> None:
        if index.isValid() and not self.proxy.is_dir(index):
            self.file_activated.emit(self.proxy.path(index))

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.tree.indexAt(pos)
        if index.isValid():
            self.item_menu_requested.emit(
                [self.proxy.path(index)], viewport_of(self.tree).mapToGlobal(pos)
            )
