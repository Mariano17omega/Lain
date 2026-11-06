"""The parts a new calculation's folder name can take besides its type and number (spec 77).

``inherited_suffix`` is the tail of the base SCF's own folder name (``1_Adsorption_teste_O11`` →
``teste_O11``); ``site_tag`` is the site atom of a molecule on a surface (``O43``, ``O43-O46``).
Both read names only, never the disk. Qt-free.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

__all__ = ["inherited_suffix", "site_tag"]

_NUMBER = re.compile(r"[0-9]+_")
_NOT_TAG = re.compile(r"[^A-Za-z0-9]")


def inherited_suffix(scf_path: Path | None) -> str:
    """What follows ``<number>_<type prefix>_`` in the name of the folder holding the SCF, or ""
    when that folder has no type prefix or nothing after it (``2_Bands``, ``Notas``). The longest
    prefix of a registered type that matches wins, without regard to case."""
    from .types import REGISTRY

    if scf_path is None:
        return ""
    name = scf_path.parent.name
    match = _NUMBER.match(name)
    if match:
        name = name[match.end() :]
    best = ""
    for calc_type in REGISTRY:
        prefix = f"{calc_type.folder_prefix}_"
        if len(prefix) > len(best) and name.lower().startswith(prefix.lower()):
            best = prefix
    return name[len(best) :] if best else ""


def site_tag(sites: Sequence[tuple[str, int]]) -> str:
    """``O43`` or ``O43-O46``: the label and the 1-based number of each site atom, ascending, with
    the characters a folder name does not take (``_SUFFIX`` of the writer) dropped from the label."""
    ordered = sorted(sites, key=lambda site: site[1])
    return "-".join(f"{_NOT_TAG.sub('', label)}{number}" for label, number in ordered)
