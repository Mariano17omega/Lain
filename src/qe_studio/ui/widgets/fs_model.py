"""Filesystem model shared by the explorer tree and the file grid."""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import QDir, QModelIndex, QSortFilterProxyModel
from PyQt6.QtGui import QFileSystemModel

from ...core.paths import is_hidden, normalize_patterns

SORT_NAME, SORT_SIZE, SORT_DATE = 0, 1, 3


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def make_fs_model(root: Path, parent=None, dot_dot: bool = False) -> QFileSystemModel:
    """``dot_dot`` lists each folder's ``..`` entry (the grid's "folder above" shortcut)."""
    model = QFileSystemModel(parent)
    dots = QDir.Filter.NoDot if dot_dot else QDir.Filter.NoDotAndDotDot
    model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | dots)
    model.setReadOnly(True)
    model.setRootPath(str(root))
    return model


class FileFilterProxy(QSortFilterProxyModel):
    """Hides configured folders (``tmp``, ``*.save``), hidden files; sorts folders first.

    A ``..`` entry (models built with ``dot_dot``) is kept below the root only, always first.
    """

    def __init__(self, hidden_dirs: list[str], dirs_only: bool = False, parent=None):
        super().__init__(parent)
        self.hidden_dirs: list[str] = []
        self.set_hidden_dirs(hidden_dirs)
        self.dirs_only = dirs_only
        self.sort_column = SORT_NAME
        self.root: Path | None = None
        self.root_prefix = ""
        self.setDynamicSortFilter(True)

    def set_hidden_dirs(self, patterns: list[str]) -> None:
        self.hidden_dirs = normalize_patterns(patterns)
        self.invalidateFilter()

    def set_root(self, root: Path) -> None:
        """Only entries below ``root`` are filtered (its ancestors may be named ``tmp``)."""
        self.root = Path(root)
        self.root_prefix = str(root).rstrip("/\\") + "/"
        self.invalidateFilter()

    @property
    def fs(self) -> QFileSystemModel:
        model = self.sourceModel()
        assert isinstance(model, QFileSystemModel)
        return model

    def path(self, index: QModelIndex) -> Path:
        """The entry's path; for ``..``, the folder above."""
        path = Path(self.fs.filePath(self.mapToSource(index)))
        return path.parent.parent if path.name == ".." else path

    def is_up(self, index: QModelIndex) -> bool:
        return self.fs.fileName(self.mapToSource(index)) == ".."

    def is_dir(self, index: QModelIndex) -> bool:
        return self.fs.isDir(self.mapToSource(index))

    def index_for(self, path: Path) -> QModelIndex:
        return self.mapFromSource(self.fs.index(str(path)))

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        index = self.fs.index(row, 0, parent)
        name = self.fs.fileName(index)
        if name == "..":  # the project root has no folder above (Lain never leaves it)
            folder = Path(self.fs.filePath(parent))
            return (
                self.root is not None and folder != self.root and folder.is_relative_to(self.root)
            )
        if self.root_prefix and not self.fs.filePath(index).startswith(self.root_prefix):
            return True
        if name.startswith("."):
            return False
        if self.fs.isDir(index):
            return not is_hidden(name, self.hidden_dirs)
        return not self.dirs_only

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        fs = self.fs
        ascending = self.sortOrder().value == 0
        left_up, right_up = fs.fileName(left) == "..", fs.fileName(right) == ".."
        if left_up or right_up:  # first in either order
            return left_up if ascending else right_up
        left_dir, right_dir = fs.isDir(left), fs.isDir(right)
        if left_dir != right_dir:
            return left_dir if ascending else right_dir
        if self.sort_column == SORT_SIZE and not left_dir:
            return fs.size(left) < fs.size(right)
        if self.sort_column == SORT_DATE:
            return fs.lastModified(left) < fs.lastModified(right)
        return _natural_key(fs.fileName(left)) < _natural_key(fs.fileName(right))
