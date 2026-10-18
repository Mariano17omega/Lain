"""The number in front of a new calculation's folder (spec 51): ``0_Relax``, ``1_Bands``, then
``2_PDOS``.

The rule reads names only, never what a folder holds: every folder of the place whose name starts
with digits and ``_`` counts, whatever its calculation type. Qt-free; lists one folder.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = ["next_number"]

_NUMBERED = re.compile(r"([0-9]+)_")


def next_number(parent: Path) -> int:
    """One more than the largest number in front of a folder of ``parent`` (``0_Relax`` and
    ``1_Bands`` → 2; ``03_bands`` counts as 3), or 0 when none has one or ``parent`` cannot be
    listed. Gaps are not reused; files, hidden names and a number with no ``_`` do not count."""
    numbers: list[int] = []
    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                match = _NUMBERED.match(entry.name)
                if match and entry.is_dir():
                    numbers.append(int(match.group(1)))
    except OSError:
        return 0
    return max(numbers, default=-1) + 1
