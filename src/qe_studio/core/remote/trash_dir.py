"""The cluster's trash (spec 84): ``<remote_root>/trash/``, where "Apagar…" of the cluster mode moves what
the user deletes. Lain never deletes anything there: emptying it is done in a terminal on the cluster.

This module only names the folder, with no import of the project, so that the fixed exclusion of a sync
of the root (``core/sync/rsync.py``), the refusal of a push into it (``core/sync/request.py``) and the
project names (``core/project/projects.py``: reserved, and its mirror here is no project) read it without
the cluster actions (``core/remote/trash.py``). Pure: nothing is read.
"""

from __future__ import annotations

from pathlib import PurePosixPath

TRASH_DIR = "trash"
# The rsync pattern of a dry run of ``remote_root`` itself (core/sync/rsync.py): anchored, so a folder
# named ``trash`` anywhere else is the user's and syncs like any other.
TRASH_EXCLUDE = "/" + TRASH_DIR + "/"


def trash_of(remote_root: str) -> str:
    """The trash folder of ``remote_root``."""
    return str(PurePosixPath(remote_root) / TRASH_DIR)


def in_trash(remote_root: str, path: str) -> bool:
    """``path`` is the trash of ``remote_root`` or lies inside it."""
    return bool(remote_root) and PurePosixPath(path).is_relative_to(trash_of(remote_root))
