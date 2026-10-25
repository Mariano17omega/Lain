"""The path on the right of the status bar (spec 16 R5.3, spec 64 R0): the folder or file selected,
relative to the project root ("." at the root), or the count of a selection of several items."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject

from ..i18n import _
from .widgets.bars import StatusBar
from .widgets.file_grid import FilePanel


class FooterPath(QObject):
    def __init__(
        self,
        status: StatusBar,
        files: FilePanel,
        root: Callable[[], Path],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.status, self.files, self._root = status, files, root
        files.file_selected.connect(self._on_file_selected)
        files.selection_changed.connect(self._on_selection_changed)

    @classmethod
    def for_window(cls, window) -> FooterPath:
        return cls(window.status, window.files, lambda: window.root, parent=window)

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._root())) or "."
        except ValueError:
            return str(path)

    def show_folder(self, folder: Path) -> None:
        self.status.set_path(self._relative(folder))

    def _on_file_selected(self, path: Path) -> None:
        if len(self.files.selected_paths()) <= 1:  # a selection of several has its own text
            self.status.set_path(self._relative(path))

    def _on_selection_changed(self, paths: list[Path]) -> None:
        if len(paths) > 1:
            self.status.set_path(_("{n} itens selecionados").format(n=len(paths)))
        else:
            self.status.set_path(self._relative(paths[0] if paths else self.files.folder))
