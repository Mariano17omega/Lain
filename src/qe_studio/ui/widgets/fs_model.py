"""Filesystem model shared by the explorer tree and the file grid."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QDir, QModelIndex, QSortFilterProxyModel, QTimer
from PyQt6.QtGui import QFileSystemModel

from ...core.file_kinds import status_label
from ...core.filtering import CategoryFilter, name_matcher
from ...core.paths import is_hidden, normalize_patterns
from ..file_types import visual_category
from ..services import DetectionService

REFILTER_DELAY_MS = 100  # detections arrive in bursts: filter once per burst

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

    The user's quick filter (spec 16 R3) comes on top: a name filter and a category filter.
    ``scope`` limits them to the entries of one folder (the grid's: the folder itself and its
    ancestors must stay), None applies them to every entry below the root and, while a filter is
    on, keeps the ancestors of what matches (the tree's). Rows are judged from caches only:
    ``service.peek_results`` for badges and ``service.file_sniff`` for states, never the disk.
    """

    def __init__(
        self,
        hidden_dirs: list[str],
        dirs_only: bool = False,
        parent=None,
        service: DetectionService | None = None,
        keep_ancestors: bool = False,
    ):
        super().__init__(parent)
        self.hidden_dirs: list[str] = []
        self.set_hidden_dirs(hidden_dirs)
        self.dirs_only = dirs_only
        self.service = service
        self.keep_ancestors = keep_ancestors
        self.sort_column = SORT_NAME
        self.root: Path | None = None
        self.root_prefix = ""
        self.name_text = ""
        self.category = CategoryFilter()
        self._name_matches: Callable[[str], bool] = name_matcher("")
        self._scope = ""  # path of the folder the filters apply to; "" = everywhere below the root
        self._refilter_timer = QTimer(self)
        self._refilter_timer.setSingleShot(True)
        self._refilter_timer.setInterval(REFILTER_DELAY_MS)
        self._refilter_timer.timeout.connect(self.invalidateFilter)
        self.setDynamicSortFilter(True)

    def set_hidden_dirs(self, patterns: list[str]) -> None:
        self.hidden_dirs = normalize_patterns(patterns)
        self.invalidateFilter()

    def set_root(self, root: Path) -> None:
        """Only entries below ``root`` are filtered (its ancestors may be named ``tmp``)."""
        self.root = Path(root)
        self.root_prefix = str(root).rstrip("/\\") + "/"
        self.invalidateFilter()

    # -- the user's filter (spec 16 R3) ----------------------------------------------------------
    @property
    def filtering(self) -> bool:
        return bool(self.name_text) or self.category.active

    def set_scope(self, folder: Path | None) -> None:
        self._scope = str(folder) if folder is not None else ""
        if self.filtering:
            self.invalidateFilter()

    def set_filters(self, name: str, category: CategoryFilter) -> None:
        """Both filters at once, with a single pass over the rows."""
        self.name_text = name
        self.category = category
        self._name_matches = name_matcher(name)
        if self.keep_ancestors:  # costs a walk down every row: only while filtering
            self.setRecursiveFilteringEnabled(self.filtering)
        self.invalidateFilter()

    def refilter_later(self) -> None:
        """A detection arrived: its folders and files may now match (or not); coalesced."""
        if self.category.active:
            self._refilter_timer.start()

    def badges_of(self, path: Path) -> list[str] | None:
        """Badges of the folder's cached detection; None while it has not run."""
        results = self.service.peek_results(path) if self.service is not None else None
        return None if results is None else [result.badge for result in results]

    def is_pending(self, index: QModelIndex) -> bool:
        """A folder shown only because its detection is still to come (badge filter on)."""
        if not self.category.badges or not self.is_dir(index) or self.is_up(index):
            return False
        return self.category.is_pending(self.badges_of(self.path(index)))

    def unfiltered_count(self, parent: QModelIndex) -> int:
        """How many entries ``parent`` would list without the user's filter (not ``..``)."""
        source = self.mapToSource(parent)
        count = 0
        for row in range(self.fs.rowCount(source)):
            index = self.fs.index(row, 0, source)
            name = self.fs.fileName(index)
            if name != ".." and self._base_accepts(index, name):
                count += 1
        return count

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
        path = self.fs.filePath(index)
        if self.root_prefix and not path.startswith(self.root_prefix):
            return True
        if not self._base_accepts(index, name):
            return False
        if not self.filtering or (self._scope and self.fs.filePath(parent) != self._scope):
            return True
        return self._user_accepts(index, name, path)

    def _base_accepts(self, index: QModelIndex, name: str) -> bool:
        """Dotfiles and ``ui.hidden_dirs`` are never shown."""
        if name.startswith("."):
            return False
        if self.fs.isDir(index):
            return not is_hidden(name, self.hidden_dirs)
        return not self.dirs_only

    def _user_accepts(self, index: QModelIndex, name: str, path: str) -> bool:
        if not self._name_matches(name):
            return False
        category = self.category
        if not category.active:
            return True
        if self.fs.isDir(index):
            return category.accepts_folder(self.badges_of(Path(path)))
        sniff = self.service.file_sniff(Path(path)) if self.service is not None else None
        label = status_label(Path(path), self.fs.size(index), sniff)
        return category.accepts_file(label[0] if label else None, visual_category(Path(path)))

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
