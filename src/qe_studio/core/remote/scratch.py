"""The scratch copy of a remote plot (spec 66): plotting a cluster folder in the cluster mode copies it
into ``<local mirror>/tmp_remote/``, and its figures and ``.plot`` go to ``tmp_remote/plots_remote/``.

A new copy overwrites what is in ``tmp_remote/`` without asking (the one exception to "never overwrite
without asking"); the folder stays until the user deletes it, is never synced (``SCRATCH_EXCLUDE``) and
is not part of its parent's detection. The rule is the name: any folder called ``tmp_remote`` exports
into ``plots_remote``, also when it is opened from the local tree. Pure: nothing is read.
"""

from __future__ import annotations

from pathlib import Path

SCRATCH_DIR = "tmp_remote"
SCRATCH_PLOTS_DIR = "plots_remote"
SCRATCH_EXCLUDE = SCRATCH_DIR + "/"  # the rsync pattern of every dry run (core/sync/rsync.py)


def scratch_of(mirror: Path) -> Path:
    """Where the cluster side of ``mirror`` is copied to be plotted."""
    return Path(mirror) / SCRATCH_DIR


def is_scratch(folder: Path) -> bool:
    """``folder`` is a scratch copy: its name is exactly ``tmp_remote``."""
    return Path(folder).name == SCRATCH_DIR
