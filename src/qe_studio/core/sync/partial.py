"""What a killed rsync leaves on the disk: ``.name.XXXXXX``, the temporary beside each file it was
writing. The name alone does not make one (``.Al.scf.in.backup`` has that shape too and is the user's),
so only a file touched since the transfer began goes. Qt-free: it runs in a worker."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable
from pathlib import Path

from .. import cancel

log = logging.getLogger(__name__)

TEMP_NAME = re.compile(r"^\.(.+)\.[A-Za-z0-9]{6}$")  # rsync's partial file for ``name``
MTIME_SLACK = 2.0  # seconds: a coarse file system, or a network home's clock
CHECK_EVERY_FOLDERS = 50


def _temp_of(name: str) -> str | None:
    match = TEMP_NAME.match(name)
    return match.group(1) if match else None


def remove_temp_files(files: Iterable[str], local_dir: Path, since: float) -> None:
    """Remove the temporaries of ``files`` (relative to ``local_dir``) that a transfer begun at
    ``since`` (epoch seconds) may have left. One listing per folder, not one per file."""
    names: dict[Path, set[str]] = {}
    for relative in files:
        target = local_dir / relative
        names.setdefault(target.parent, set()).add(target.name)
    for folder, expected in cancel.checked(names.items(), CHECK_EVERY_FOLDERS):
        try:
            with os.scandir(folder) as entries:
                temps = [entry for entry in entries if _temp_of(entry.name) in expected]
        except OSError:
            continue
        for entry in temps:
            try:
                if entry.stat(follow_symlinks=False).st_mtime >= since - MTIME_SLACK:
                    os.remove(entry.path)
                    log.info("sync: removed the partial file %s", entry.path)
            except OSError:
                continue
