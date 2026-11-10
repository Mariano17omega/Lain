"""The bytes of an image the workspace shows (a PNG, JPG or SVG export), read in a worker.

Qt-free. The disk read is here, not in ``ui/`` (which never touches the disk): the image viewer runs
:func:`read_image` through ``core/tasks.run_task`` and decodes the bytes there too, so opening a
large export, or one on a slow mount, never stops the window.
"""

from __future__ import annotations

from pathlib import Path

from ..cancel import check


def read_image(path: Path) -> bytes:
    """The whole file; ``OSError`` when it cannot be read (the viewer then stays blank)."""
    check()
    return path.read_bytes()
