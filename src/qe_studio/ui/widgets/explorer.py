"""Folder explorer: project tree with calculation badges (PRD §2.1.2 navigation mode)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ..file_types import file_visual, human_size
from ..painting import mono_font, paint_badge, ui_font
from ..services import DetectionService
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader
from .fs_model import FileFilterProxy, make_fs_model

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
                right = paint_badge(painter, right, center, result.badge, self.theme) - 4
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

    def _paint_file_meta(
        self, painter: QPainter, path: Path, size: int, right: float, rect: QRect
    ) -> float:
        sniff = self.service.file_sniff(path)
        painter.setFont(mono_font(10))
        if sniff is not None and sniff.is_output and sniff.job_done is not None:
            text, token = (
                ("OK", "success")
                if sniff.job_done and not sniff.warnings
                else (("INCOMPLETO", "warning") if not sniff.job_done else ("AVISO", "warning"))
            )
        else:
            text, token = human_size(size), "text_dim"
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

        self.model = make_fs_model(root, self)
        self.proxy = FileFilterProxy(hidden_dirs, parent=self)
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
        self.tree.setItemDelegate(ExplorerDelegate(theme, service, self.proxy))
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.tree, 1)

        self.set_root(root)
        self.tree.selectionModel().currentChanged.connect(self._on_current)
        self.tree.activated.connect(self._on_activated)  # double click or Enter
        self.collapse_button.clicked.connect(self.tree.collapseAll)
        self.refresh_button.clicked.connect(self.refresh)
        service.detected.connect(lambda _folder: self.tree.viewport().update())
        theme.theme_changed.connect(lambda _name: self.tree.viewport().update())

    @property
    def root(self) -> Path:
        return self._root

    def set_root(self, root: Path) -> None:
        self._root = Path(root)
        self.proxy.set_root(self._root)
        self.model.setRootPath(str(root))
        self.tree.setRootIndex(self.proxy.index_for(root))

    def refresh(self) -> None:
        self.service.invalidate()
        self.tree.viewport().update()

    def current_path(self) -> Path | None:
        index = self.tree.currentIndex()
        return self.proxy.path(index) if index.isValid() else None

    def current_folder(self) -> Path:
        path = self.current_path()
        if path is None:
            return self._root
        return path if path.is_dir() else path.parent

    def select_path(self, path: Path) -> None:
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
