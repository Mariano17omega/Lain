"""Filesystem model shared by the explorer tree and the file grid."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from PyQt6.QtCore import QDir, QModelIndex, QSortFilterProxyModel
from PyQt6.QtGui import QFileSystemModel

SORT_NAME, SORT_SIZE, SORT_DATE = 0, 1, 3


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def make_fs_model(root: Path, parent=None) -> QFileSystemModel:
    model = QFileSystemModel(parent)
    model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
    model.setReadOnly(True)
    model.setRootPath(str(root))
    return model


class FileFilterProxy(QSortFilterProxyModel):
    """Hides configured folders (``tmp``, ``*.save``), hidden files; sorts folders first."""

    def __init__(self, hidden_dirs: list[str], dirs_only: bool = False, parent=None):
        super().__init__(parent)
        self.hidden_dirs: list[str] = []
        self.set_hidden_dirs(hidden_dirs)
        self.dirs_only = dirs_only
        self.sort_column = SORT_NAME
        self.root_prefix = ""
        self.setDynamicSortFilter(True)

    def set_hidden_dirs(self, patterns: list[str]) -> None:
        self.hidden_dirs = [pattern.rstrip("/").lower() for pattern in patterns]
        self.invalidateFilter()

    def set_root(self, root: Path) -> None:
        """Only entries below ``root`` are filtered (its ancestors may be named ``tmp``)."""
        self.root_prefix = str(root).rstrip("/\\") + "/"
        self.invalidateFilter()

    @property
    def fs(self) -> QFileSystemModel:
        return self.sourceModel()

    def path(self, index: QModelIndex) -> Path:
        return Path(self.fs.filePath(self.mapToSource(index)))

    def is_dir(self, index: QModelIndex) -> bool:
        return self.fs.isDir(self.mapToSource(index))

    def index_for(self, path: Path) -> QModelIndex:
        return self.mapFromSource(self.fs.index(str(path)))

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        index = self.fs.index(row, 0, parent)
        if self.root_prefix and not self.fs.filePath(index).startswith(self.root_prefix):
            return True
        name = self.fs.fileName(index)
        if name.startswith("."):
            return False
        if self.fs.isDir(index):
            lowered = name.lower()
            return not any(fnmatch.fnmatch(lowered, pattern) for pattern in self.hidden_dirs)
        return not self.dirs_only

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        fs = self.fs
        left_dir, right_dir = fs.isDir(left), fs.isDir(right)
        if left_dir != right_dir:
            ascending = self.sortOrder().value == 0
            return left_dir if ascending else right_dir
        if self.sort_column == SORT_SIZE and not left_dir:
            return fs.size(left) < fs.size(right)
        if self.sort_column == SORT_DATE:
            return fs.lastModified(left) < fs.lastModified(right)
        return _natural_key(fs.fileName(left)) < _natural_key(fs.fileName(right))
