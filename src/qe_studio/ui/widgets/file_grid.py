"""File view of the active simulation: cards (grid) or rows (list) (PRD §2.1.3)."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QActionGroup, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..file_types import file_visual, human_size
from ..painting import mono_font
from ..services import DetectionService
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader
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
                path.name, Qt.TextElideMode.ElideMiddle, name_rect.width()
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
                path.name, Qt.TextElideMode.ElideMiddle, name_rect.width()
            )
            painter.drawText(
                name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name
            )
        painter.restore()

    def _meta(self, path: Path, is_dir: bool, size: int) -> tuple[str, str]:
        if is_dir:
            count = self.panel.item_count(path)
            return (f"{count} itens" if count is not None else "pasta"), "text_dim"
        sniff = self.panel.service.file_sniff(path)
        if sniff is not None and sniff.is_output and sniff.job_done is not None:
            if not sniff.job_done:
                return f"{human_size(size)} · incompleto", "warning"
            return f"{human_size(size)} · OK", "success"
        return human_size(size), "text_dim"


class FilePanel(QWidget):
    file_activated = pyqtSignal(Path)
    folder_activated = pyqtSignal(Path)
    file_selected = pyqtSignal(Path)

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
        self._counts: dict[str, int] = {}
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

        self.model = make_fs_model(root, self)
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
        self.proxy.sort(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.view, 1)
        self._apply_mode()

        self.grid_button.clicked.connect(lambda: self.set_grid_mode(True))
        self.list_button.clicked.connect(lambda: self.set_grid_mode(False))
        self.view.activated.connect(self._on_activated)
        self.view.selectionModel().currentChanged.connect(self._on_current)
        self.model.directoryLoaded.connect(self._update_count)
        self.proxy.rowsInserted.connect(self._update_count)
        self.proxy.rowsRemoved.connect(self._update_count)
        service.detected.connect(lambda _f: self.view.viewport().update())
        theme.theme_changed.connect(lambda _n: self.view.viewport().update())
        self.set_folder(root)

    @property
    def folder(self) -> Path:
        return self._folder

    def set_folder(self, folder: Path) -> None:
        self._folder = Path(folder)
        self.model.setRootPath(str(folder))
        self.view.setRootIndex(self.proxy.index_for(folder))
        self.service.results(self._folder)  # warm the sniff cache for status labels
        self._update_count()

    def refresh(self) -> None:
        self._counts.clear()
        self.view.viewport().update()

    def set_grid_mode(self, grid: bool) -> None:
        self.grid_mode = grid
        self.grid_button.setChecked(grid)
        self.list_button.setChecked(not grid)
        self._apply_mode()

    def select_file(self, path: Path) -> None:
        index = self.proxy.index_for(path)
        if index.isValid():
            self.view.setCurrentIndex(index)

    def item_count(self, folder: Path) -> int | None:
        key = str(folder)
        if key not in self._counts:
            try:
                self._counts[key] = sum(1 for e in os.scandir(folder) if not e.name.startswith("."))
            except OSError:
                return None
        return self._counts[key]

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
        view.doItemsLayout()

    def _sort_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        for label, column in (("Nome", SORT_NAME), ("Tamanho", SORT_SIZE), ("Data", SORT_DATE)):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(column == SORT_NAME)
            group.addAction(action)
            action.triggered.connect(lambda _c=False, col=column: self._sort(col))
        return menu

    def _sort(self, column: int) -> None:
        self.proxy.sort_column = column
        self.proxy.invalidate()
        order = Qt.SortOrder.AscendingOrder if column == SORT_NAME else Qt.SortOrder.DescendingOrder
        self.proxy.sort(0, order)

    def _update_count(self, *_args) -> None:
        root = self.view.rootIndex()
        self.header.count.setText(f"({self.proxy.rowCount(root)})")

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
