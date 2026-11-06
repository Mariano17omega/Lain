"""The element of a pw.x species label, its covalent radius and atomic number (spec 40 R2.2).

The rule is ASE's ``label_to_symbol`` (two letters when they are a symbol, else one: ``Fe1``,
``Fe_up`` → Fe; ``C2`` → C) and the radii are ``ase.data.covalent_radii``, the table the user's
scripts use. ``ase.data`` is imported on first use only (about 8 ms; never ``ase.io``).
"""

from __future__ import annotations

import functools

from ....i18n import _
from . import SurfaceError

__all__ = ["atomic_number", "covalent_radius", "element_of"]


@functools.cache
def _symbols() -> dict[str, int]:
    from ase.data import chemical_symbols

    return {symbol: number for number, symbol in enumerate(chemical_symbols) if number > 0}


@functools.cache
def element_of(label: str) -> str:
    """The chemical symbol of a species label. Raises ``SurfaceError``."""
    symbols = _symbols()
    if len(label) >= 2 and (two := label[0].upper() + label[1].lower()) in symbols:
        return two
    if label[:1].upper() in symbols:
        return label[:1].upper()
    raise SurfaceError(_("Espécie sem elemento conhecido: {label}").format(label=label))


def atomic_number(label: str) -> int:
    return _symbols()[element_of(label)]


def covalent_radius(label: str) -> float:
    """In Å."""
    from ase.data import covalent_radii

    return float(covalent_radii[atomic_number(label)])
