"""Writing a cell as ``CELL_PARAMETERS`` with ``ibrav = 0`` (spec 24, spec 40 R2.4).

The cell's geometry is then the card alone: ``ibrav = 0`` and none of the keys that describe a Bravais
lattice (``A``, ``B``, ``C``, the cosines and ``celldm(i)``), except ``celldm(1)`` for an ``alat``
card, whose rows are in its units. The rest of the input stays as written (``InputEditor``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .input_edit import InputEditor

__all__ = ["set_cell"]

CELL_KEYS = frozenset({"a", "b", "c", "cosab", "cosac", "cosbc"})
_CELLDM = re.compile(r"celldm\((\d)\)")


def set_cell(
    editor: InputEditor,
    unit: str,
    rows: Sequence[str],
    alat: str | None = None,
    *,
    cell: str = "a célula",
) -> str | None:
    """Write ``rows`` (as they go in the file) as ``CELL_PARAMETERS unit`` with ``ibrav = 0``;
    ``alat`` is the value of ``celldm(1)`` of an ``alat`` card. Returns the note of an ``ibrav`` that
    was not 0 (``cell`` names what the card holds in it), else None."""
    ibrav = editor.get("system", "ibrav")
    editor.replace_card("CELL_PARAMETERS", unit, list(rows))
    editor.set("system", "ibrav", "0")
    for key in editor.keys("system"):
        celldm = _CELLDM.fullmatch(key)
        if key in CELL_KEYS or (celldm and not (unit == "alat" and celldm.group(1) == "1")):
            editor.remove("system", key)
    if unit == "alat" and alat is not None:
        editor.set("system", "celldm(1)", alat)  # the unit of the rows
    if ibrav is not None and ibrav.strip() != "0":
        return f"ibrav = {ibrav.strip()} trocado por 0: {cell} vai em CELL_PARAMETERS"
    return None
