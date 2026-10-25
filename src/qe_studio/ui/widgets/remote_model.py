"""Models of the cluster mode's panels (spec 65 R4): the folders of the tree, listed as they are
opened, and the rows of the folder the grid shows. They hold what the controller hands them (the
listings of ``core/remote/listing.py``) and never list anything themselves: an item opened for the
first time asks for its subfolders (``fetch_requested``)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import NamedTuple

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QStandardItem, QStandardItemModel

from ...core.file_kinds import human_size
from ...core.remote.listing import RemoteEntry
from ...core.sync.preview import format_mtime
from ...i18n import _
from ..file_types import file_visual
from ..theme.manager import ThemeManager

DIR_ROLE = Qt.ItemDataRole.UserRole + 1  # the folder's path on the cluster
ICON_PX = 16
NO_INDEX = QModelIndex()  # the default parent: the root
COLUMNS = (_("Nome"), _("Tamanho"), _("Modificado"))
UP = ".."


class RemotePath(NamedTuple):
    """An item of the cluster: its path there, and whether it is a folder."""

    path: str
    is_dir: bool


class RemoteTreeModel(QStandardItemModel):
    """The folders below ``top`` (the invisible root). An item not listed yet shows an arrow; opening
    it asks for its subfolders once, and a listing without any takes the arrow away. A folder whose
    listing failed is not asked for again until ``retry_failed`` (the view would fetch the root by
    itself, and a refused login must not be tried again on its own)."""

    fetch_requested = pyqtSignal(str)  # the folder whose subfolders the tree wants

    def __init__(self, theme: ThemeManager, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.top = ""
        self._items: dict[str, QStandardItem] = {}
        self._listed: set[str] = set()
        self._requested: set[str] = set()
        self._failed: set[str] = set()

    def reset(self, top: str) -> None:
        """An empty tree under ``top`` (the mode turned on, another project)."""
        self.clear()
        self.setColumnCount(1)
        self.top = top
        self._items, self._listed, self._requested, self._failed = {}, set(), set(), set()

    def dir_of(self, index: QModelIndex) -> str:
        if not index.isValid():
            return self.top
        item = self.itemFromIndex(index)
        return item.data(DIR_ROLE) if item is not None else self.top

    def index_for(self, remote_dir: str) -> QModelIndex:
        """The row of ``remote_dir``; invalid for ``top`` and for folders not listed yet."""
        item = self._items.get(remote_dir)
        return item.index() if item is not None else QModelIndex()

    def _item_for(self, remote_dir: str) -> QStandardItem | None:
        if remote_dir == self.top:
            return self.invisibleRootItem()
        return self._items.get(remote_dir)

    # -- listed on demand ------------------------------------------------------------------------
    def hasChildren(self, parent: QModelIndex = NO_INDEX) -> bool:
        if parent.isValid() and parent.column() > 0:
            return False
        if self.dir_of(parent) not in self._listed:
            return True
        return super().hasChildren(parent)

    def canFetchMore(self, parent: QModelIndex) -> bool:
        remote_dir = self.dir_of(parent)
        return remote_dir not in self._listed and remote_dir not in self._requested

    def fetchMore(self, parent: QModelIndex) -> None:
        self.request(self.dir_of(parent))

    def request(self, remote_dir: str) -> None:
        """Ask for the subfolders of ``remote_dir`` unless they are listed or asked for already."""
        if remote_dir in self._listed or remote_dir in self._requested:
            return
        self._requested.add(remote_dir)
        self.fetch_requested.emit(remote_dir)

    def mark_failed(self, remote_dir: str) -> None:
        """The listing of ``remote_dir`` failed: asked for again after ``retry_failed`` only."""
        self._failed.add(remote_dir)

    def retry_failed(self) -> None:
        """The user asked to list again: the folders that failed may be asked for again."""
        self._requested -= self._failed
        self._failed.clear()

    def set_subfolders(self, remote_dir: str, names: list[str]) -> None:
        """The subfolders of ``remote_dir`` (sorted), merged with its rows: the gone ones leave,
        the new ones come in order, and the others keep what was listed below them."""
        parent = self._item_for(remote_dir)
        if parent is None:  # a folder the tree has not reached: its parent was never listed
            return
        self._requested.discard(remote_dir)
        self._failed.discard(remote_dir)
        was_listed = remote_dir in self._listed
        self._listed.add(remote_dir)
        wanted = set(names)
        for row in reversed(range(parent.rowCount())):
            child = parent.child(row)
            if child is not None and child.text() not in wanted:
                self._forget(child)
                parent.removeRow(row)
        kept = [child.text() for row in range(parent.rowCount()) if (child := parent.child(row))]
        if kept != [name for name in names if name in set(kept)]:  # another order: start over
            for child in kept:
                self._forget_path(PurePosixPath(remote_dir) / child)
            parent.removeRows(0, parent.rowCount())
        row = 0
        for name in names:
            child = parent.child(row)
            if child is not None and child.text() == name:
                row += 1
                continue
            parent.insertRow(row, self._new_item(remote_dir, name))
            row += 1
        if not names and not was_listed:  # no subfolder: the view drops the arrow it drew
            self.layoutAboutToBeChanged.emit()
            self.layoutChanged.emit()

    def _new_item(self, remote_dir: str, name: str) -> QStandardItem:
        path = str(PurePosixPath(remote_dir) / name)
        item = QStandardItem(name)
        item.setEditable(False)
        item.setData(path, DIR_ROLE)
        item.setToolTip(path)
        self._items[path] = item
        return item

    def _forget(self, item: QStandardItem) -> None:
        self._forget_path(PurePosixPath(item.data(DIR_ROLE)))

    def _forget_path(self, path: PurePosixPath) -> None:
        """``path`` and everything below it leave the lookups."""
        for known in [p for p in self._items if PurePosixPath(p).is_relative_to(path)]:
            del self._items[known]
            self._listed.discard(known)
            self._requested.discard(known)
            self._failed.discard(known)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole and index.isValid():
            icon, token = file_visual(Path(), True)
            return self.theme.icon(icon, token, size=ICON_PX)
        return super().data(index, role)


class RemoteFileModel(QAbstractTableModel):
    """The entries of one folder of the cluster: name, size, date; ``..`` first below the top."""

    def __init__(self, theme: ThemeManager, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.folder = ""
        self.up: str | None = None  # the folder above; None at the top
        self.entries: list[RemoteEntry] = []

    def set_rows(self, folder: str, entries: list[RemoteEntry], up: str | None) -> None:
        self.beginResetModel()
        self.folder, self.entries, self.up = folder, list(entries), up
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = NO_INDEX) -> int:
        return 0 if parent.isValid() else len(self.entries) + (self.up is not None)

    def columnCount(self, parent: QModelIndex = NO_INDEX) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def is_up(self, index: QModelIndex) -> bool:
        return index.isValid() and self.up is not None and index.row() == 0

    def entry(self, index: QModelIndex) -> RemoteEntry | None:
        if not index.isValid() or self.is_up(index):
            return None
        return self.entries[index.row() - (self.up is not None)]

    def path_of(self, index: QModelIndex) -> RemotePath | None:
        """The item of the row: ``..`` is the folder above."""
        if self.is_up(index):
            return RemotePath(self.up or "", True)
        entry = self.entry(index)
        if entry is None:
            return None
        return RemotePath(str(PurePosixPath(self.folder) / entry.name), entry.is_dir)

    def row_of(self, name: str) -> int | None:
        for row, entry in enumerate(self.entries):
            if entry.name == name:
                return row + (self.up is not None)
        return None

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        column, entry = index.column(), self.entry(index)
        name, is_dir = (UP, True) if entry is None else (entry.name, entry.is_dir)
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return name
            if entry is None:
                return ""
            if column == 1:
                return "" if is_dir else human_size(entry.size)
            return format_mtime(entry.mtime)
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            icon, token = file_visual(Path(name), is_dir)
            return self.theme.icon(icon, token, size=ICON_PX)
        if role == Qt.ItemDataRole.ForegroundRole and column > 0:
            return QBrush(self.theme.color("text_meta"))
        if role == Qt.ItemDataRole.TextAlignmentRole and column == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ToolTipRole and column == 0 and entry is not None:
            return _("{name} (link simbólico)").format(name=name) if entry.link else name
        return None
