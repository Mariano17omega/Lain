"""The "FAVORITOS" and "RECENTES" sections above the explorer tree (spec 16 R4): a collapsible
header and a short list of folders. A click goes to the folder, a right click opens the usual
item menu. A folder that no longer exists is dimmed."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..theme.manager import ThemeManager
from ..theme.scale import scaled
from .common import set_variant, viewport_of

ROW_HEIGHT = 22
MAX_ROWS = 6  # more scroll inside the section


class NavEntry(NamedTuple):
    path: Path
    label: str
    exists: bool


class NavSection(QWidget):
    folder_requested = pyqtSignal(Path)
    menu_requested = pyqtSignal(list, QPoint)  # [folder], global position
    toggled = pyqtSignal(bool)  # opened / closed by the user

    def __init__(
        self,
        theme: ThemeManager,
        title: str,
        icon: str,
        icon_token: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.theme, self.title, self.icon, self.icon_token = theme, title, icon, icon_token
        self._entries: list[NavEntry] = []
        self.setObjectName("navSection")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.header = set_variant(QToolButton(), "sectionHeader")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setIconSize(QSize(14, 14))
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.list = QListWidget()
        self.list.setObjectName("navList")
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.setIconSize(QSize(14, 14))
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        column.addWidget(self.header)
        column.addWidget(self.list)
        self.header.toggled.connect(self._on_toggled)
        self.list.itemClicked.connect(self._on_clicked)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        theme.theme_changed.connect(self._render)
        theme.scale_changed.connect(self._render)
        self.hide()  # until there is something to list

    # -- content ---------------------------------------------------------------------------------
    @property
    def entries(self) -> list[NavEntry]:
        return list(self._entries)

    def labels(self) -> list[str]:
        return [entry.label for entry in self._entries]

    def set_entries(self, entries: list[NavEntry]) -> None:
        self._entries = list(entries)
        self._render()

    def set_open(self, opened: bool) -> None:
        self.header.setChecked(opened)

    def _render(self, *_args) -> None:
        self.list.clear()
        for entry in self._entries:
            item = QListWidgetItem(self.theme.icon(self.icon, self.icon_token), entry.label)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            item.setSizeHint(QSize(0, scaled(ROW_HEIGHT)))
            if entry.exists:
                item.setToolTip(str(entry.path))
            else:
                item.setToolTip("não encontrada")
                item.setForeground(self.theme.color("text_meta"))
            self.list.addItem(item)
        self.header.setText(f"{self.title.upper()} ({len(self._entries)})")
        self._sync_header_icon()
        self.list.setFixedHeight(min(len(self._entries), MAX_ROWS) * scaled(ROW_HEIGHT) + 2)
        self.setVisible(bool(self._entries))

    def _sync_header_icon(self) -> None:
        name = "expand_more" if self.header.isChecked() else "chevron_right"
        self.header.setIcon(self.theme.icon(name, "text_muted", size=14))

    # -- interaction -----------------------------------------------------------------------------
    def _on_toggled(self, opened: bool) -> None:
        self.list.setVisible(opened)
        self._sync_header_icon()
        self.toggled.emit(opened)

    def _path_of(self, item: QListWidgetItem | None) -> Path | None:
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _on_clicked(self, item: QListWidgetItem) -> None:
        path = self._path_of(item)
        if path is not None:
            self.folder_requested.emit(path)

    def _on_context_menu(self, pos: QPoint) -> None:
        path = self._path_of(self.list.itemAt(pos))
        if path is not None:
            self.menu_requested.emit([path], viewport_of(self.list).mapToGlobal(pos))
