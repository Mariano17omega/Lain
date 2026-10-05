"""Renaming a file or folder from the context menu (spec 5 R3.4), refused while something works
inside it (spec 27-3 R2).

Renaming touches global state, so it lives apart from the panels: the pending ``.plot`` settings go
into the folder before it moves, the tabs, history, favorites, folder memory and grids that name it
follow, and the detection cache forgets it. A pull, push, export, derived SCF or new calculation
that writes there would land in the old path (and an export would recreate it), so ``blocked`` says
no first; each of those is a *blocker*, a function from the path to a reason or ``None``, built by
``for_window`` from the controller that knows about it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox, QWidget

from ..core.file_ops import overlaps, rename_item
from .dialogs.rename import ask_rename

log = logging.getLogger(__name__)

TITLE = "Renomear"
EXPORTING = "Há uma exportação de figura em andamento. Espere terminar e tente de novo."

# What stops a rename: the path being renamed → why (Portuguese), or None.
Blocker = Callable[[Path], str | None]


def sync_blocker(sync) -> Blocker:
    """A pull or a push of a folder that contains the path, lies inside it or is the root."""

    def reason(path: Path) -> str | None:
        folder = sync.folder
        if folder is None or not overlaps(folder, path):
            return None
        scope = sync.scope
        where = scope.relative if scope is not None and scope.relative else "toda a pasta raiz"
        what = "um envio ao cluster" if scope is not None and scope.push else "uma sincronização"
        return f"Há {what} em andamento em {where}. Espere terminar ou cancele."

    return reason


def export_blocker(exporting: Callable[[], bool]) -> Blocker:
    def reason(_path: Path) -> str | None:
        return EXPORTING if exporting() else None

    return reason


def derive_blocker(derive) -> Blocker:
    def reason(path: Path) -> str | None:
        output = derive.active_under(path)
        if output is None:
            return None
        return f"Há um SCF convergido sendo gerado a partir de {output.name}. Espere terminar."

    return reason


def create_blocker(calc_create) -> Blocker:
    def reason(path: Path) -> str | None:
        folder = calc_create.creating_under(path)
        if folder is None:
            return None
        return f"Há um cálculo sendo criado em {folder.name}. Espere terminar."

    return reason


class RenameController:
    def __init__(
        self,
        dialog_parent: QWidget,
        blockers: Sequence[Blocker],
        *,
        wait_for_exports: Callable[[], bool],
        flush_settings: Callable[[Path], None],
        current_folder: Callable[[], Path],
        tree_path: Callable[[], Path | None],
        close_tabs_under: Callable[[Path], None],
        moved: Sequence[Callable[[Path, Path, Path, Path], None]],
        invalidate: Callable[[Path], None],
        select_in_tree: Callable[[Path], None],
        grid_folder: Callable[[], Path],
        select_in_grid: Callable[[Path], None],
        message: Callable[[str, int], None],
    ):
        self._parent = dialog_parent
        self._blockers = list(blockers)
        self._wait_for_exports, self._flush_settings = wait_for_exports, flush_settings
        self._current_folder, self._tree_path = current_folder, tree_path
        self._close_tabs_under, self._moved, self._invalidate = close_tabs_under, moved, invalidate
        self._select_in_tree, self._grid_folder = select_in_tree, grid_folder
        self._select_in_grid, self._message = select_in_grid, message

    @classmethod
    def for_window(cls, window) -> RenameController:
        """The controller of a ``MainWindow``: the panels, tabs and stores a rename has to tell."""

        def moved(old: Path, new: Path, old_resolved: Path, new_resolved: Path) -> None:
            window.navigation.rename(old, new)
            window.memory.rename(old_resolved, new_resolved)
            window.grids.rename(old_resolved, new_resolved)
            window.project.reload()  # a first-level folder is a project (spec 31)

        blockers = [
            sync_blocker(window.sync),
            export_blocker(lambda: window.plot_workflow.exporting),
            derive_blocker(window.derive),
            create_blocker(window.calc_create),
        ]
        return cls(
            window,
            blockers,
            wait_for_exports=window.plot_workflow.wait_for_exports,
            flush_settings=lambda path: window.plot_settings.flush_now(inside=path),
            current_folder=window.current_folder,
            tree_path=window.explorer.current_path,
            close_tabs_under=window.workspace.close_tabs_under,
            moved=[moved],
            invalidate=window.service.invalidate,
            select_in_tree=window.explorer.select_path,
            grid_folder=lambda: window.files.folder,
            select_in_grid=window.files.select_file,
            message=lambda text, ms: window.status.set_message(text, timeout_ms=ms),
        )

    def blocked(self, path: Path) -> str | None:
        """Why ``path`` cannot be renamed now (Portuguese), None when it can."""
        for blocker in self._blockers:
            if (reason := blocker(path)) is not None:
                return reason
        return None

    def _refuse(self, reason: str) -> None:
        QMessageBox.information(self._parent, TITLE, reason)

    def rename(self, path: Path) -> None:
        """Rename a file or folder; tabs showing anything inside it are closed (spec 5 R3.4)."""
        if (reason := self.blocked(path)) is not None:
            self._refuse(reason)
            return
        name = ask_rename(self._parent, path)
        if name is None:
            return
        # An export that started while the dialog was open must not recreate the old folder after
        # the move. Waiting comes before the settings are written, so a refusal changes nothing.
        if not self._wait_for_exports():
            self._refuse(EXPORTING)
            return
        # Pending plot settings go into the folder before it moves, so they travel with it.
        self._flush_settings(path)
        current = self._current_folder()
        tree_had_it = self._tree_path() == path
        old_resolved = path.resolve()
        try:
            new = rename_item(path, name)
        except OSError as exc:
            log.warning("rename %s → %s failed: %s", path, name, exc)
            QMessageBox.warning(
                self._parent, TITLE, f"Não foi possível renomear {path.name}: {exc.strerror or exc}"
            )
            return
        self._close_tabs_under(path)
        new_resolved = new.resolve()
        for update in self._moved:
            update(path, new, old_resolved, new_resolved)
        self._invalidate(path.parent)
        if current.is_relative_to(path):
            self._select_in_tree(new / current.relative_to(path))
        elif tree_had_it:
            self._select_in_tree(new)
        if new.parent == self._grid_folder():
            self._select_in_grid(new)
        self._message(f"Renomeado: {path.name} → {new.name}", 4000)
