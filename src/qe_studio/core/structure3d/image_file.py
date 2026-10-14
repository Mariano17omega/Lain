"""Where the "Print" of the 3D window goes (spec 46 R5): ``<simulation>/plots/<name>-3d.png``.

The name follows the figures' convention (spec 32: the folders from the project root, then the file's own
name) and a file that exists is never overwritten: the next free ``_2``, ``_3``… is taken, with an
exclusive create, so two windows (or two clicks) never choose the same name. Qt-free: the window encodes
the image, this only names and writes the bytes.
"""

from __future__ import annotations

from pathlib import Path

from ..plotting.names import PLOTS_DIR, export_prefix, join_stem
from ..unique_names import write_new_bytes

__all__ = ["SUFFIX", "print_stem", "save_png"]

SUFFIX = "-3d"


def print_stem(source_path: str | Path, root: str | Path | None) -> str:
    """``<local_root>/ilita/Analise_1/scf.in`` → ``ilita-Analise_1-scf-3d``.

    ``root`` is the project root: the input in the root itself has no prefix (``scf-3d``); outside it, or
    without a ``root``, the prefix is the name of the input's folder (``Analise_1-scf-3d``). Pure: nothing
    is read from the disk."""
    path = Path(source_path)
    folder = path.parent
    prefix = folder.name if root is None else export_prefix(folder, Path(root))
    return join_stem(prefix, f"{path.stem}{SUFFIX}")


def save_png(folder: str | Path, stem: str, data: bytes) -> Path:
    """Write ``data`` as ``<folder>/plots/<stem>.png`` (or the first free ``<stem>_N.png``, from 2).

    ``plots/`` is made if missing, but never ``folder`` itself: a simulation folder that is gone is a
    ``FileNotFoundError``, not a new empty tree under the old name."""
    plots = Path(folder) / PLOTS_DIR
    plots.mkdir(exist_ok=True)
    return write_new_bytes(plots / f"{stem}.png", data, first=2)
