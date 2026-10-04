"""Helpers shared by the file grid tests (menu, selection, filters)."""

from pathlib import Path

from PyQt6.QtCore import QItemSelectionModel, Qt


def rows(panel):
    root = panel.view.rootIndex()
    return [panel.proxy.index(r, 0, root) for r in range(panel.proxy.rowCount(root))]


def show_folder(qtbot, window, folder: Path, up: bool = True) -> None:
    """Select ``folder`` in the tree and wait until the grid lists it (with ".." first)."""
    window.explorer.select_path(folder)

    def listed():
        items = rows(window.files)
        return (
            window.files.folder == folder
            and len(items) > 1
            and (window.files.proxy.is_up(items[0]) == up)
        )

    qtbot.waitUntil(listed, timeout=5000)


def menu_texts(menu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def index_of(panel, name: str):
    """The grid's index of the entry called ``name``."""
    for index in rows(panel):
        if not panel.proxy.is_up(index) and panel.proxy.path(index).name == name:
            return index
    raise AssertionError(f"{name} is not listed: {[panel.proxy.path(i).name for i in rows(panel)]}")


def click(qtbot, panel, name: str, ctrl: bool = False, shift: bool = False) -> None:
    """A real mouse click on the card or row of ``name``."""
    modifiers = Qt.KeyboardModifier.NoModifier
    if ctrl:
        modifiers |= Qt.KeyboardModifier.ControlModifier
    if shift:
        modifiers |= Qt.KeyboardModifier.ShiftModifier
    view = panel.view
    pos = view.visualRect(index_of(panel, name)).center()
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, modifiers, pos)
    reset_modifiers(qtbot, view.viewport())


def reset_modifiers(qtbot, widget) -> None:
    """Qt keeps the modifiers of the last simulated event (``QGuiApplication.keyboardModifiers``,
    which ``setCurrentIndex`` reads): a plain mouse move forgets a Ctrl or Shift."""
    qtbot.mouseMove(widget)


def select_names(panel, *names: str) -> list[Path]:
    """Replace the selection with the entries called ``names``; the selected paths."""
    selection = panel.view.selectionModel()
    selection.clearSelection()
    for name in names:
        selection.select(index_of(panel, name), QItemSelectionModel.SelectionFlag.Select)
    return panel.selected_paths()


def names(panel) -> list[str]:
    """What the grid lists, in order; ".." for the folder-above entry."""
    return [".." if panel.proxy.is_up(i) else panel.proxy.path(i).name for i in rows(panel)]


def tree_names(window, parent=None) -> list[str]:
    """What the explorer tree lists below ``parent`` (a proxy index; default: the project)."""
    tree = window.explorer
    if parent is None:
        parent = tree.tree.rootIndex()
    return [
        tree.proxy.path(tree.proxy.index(r, 0, parent)).name
        for r in range(tree.proxy.rowCount(parent))
    ]
