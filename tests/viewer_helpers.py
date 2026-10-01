"""Shared by the text viewer tests (test_text_viewer.py, test_input_view.py)."""

from pathlib import Path

from PyQt6.QtCore import Qt

from qe_studio.ui.widgets.text_viewer import TextViewer

ENTER = 0x01000004  # Qt.Key.Key_Return
ESCAPE = 0x01000000
CTRL = 0x04000000  # Qt.KeyboardModifier.ControlModifier
SHIFT = 0x02000000


def open_text(qtbot, window, path: Path) -> TextViewer:
    """Open ``path`` in the workspace and wait for the worker to hand the text over."""
    window.open_file(path)
    viewer = window.workspace.widget_for(str(path))
    assert isinstance(viewer, TextViewer)
    with qtbot.waitSignal(viewer.loaded, timeout=5000):
        pass
    return viewer


def key(qtbot, widget, name: str, modifiers: int = 0) -> None:
    qtbot.keyClick(widget, getattr(Qt.Key, f"Key_{name}"), Qt.KeyboardModifier(modifiers))
