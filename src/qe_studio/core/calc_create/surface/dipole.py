"""The saw-like field of a slab and its dipole correction (spec 98 R1, spec 105): where the ramp goes
and the keys that write it.

pw.x adds a saw-like potential with ``tefield`` (``&CONTROL``; ``edir``, ``emaxpos``, ``eopreg`` and
``eamp`` in ``&SYSTEM``) and, with ``dipfield`` too, Bengtsson's dipole correction. The potential falls
over ``[emaxpos, emaxpos + eopreg]``, wrapped into the cell (``PW/src/extfield.f90:67-89``). Nothing in
pw.x checks that this ramp lies in the vacuum ("or else unphysical forces will result", ``INPUT_PW``),
so a window nobody typed is put in the middle of the widest empty gap, along ``edir``, of the structure
the type writes. ``edir = 3`` follows the third reciprocal vector, so a tilted c works. ``eamp`` is
always written: the doc says its default is 0.001 a.u., the code 0
(``Modules/read_namelists.f90:251-254``). Qt-free.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ...qe.input_edit import InputEditor
from ..edits import put_number
from .geometry import interplanar, widest_gap

__all__ = [
    "CONTROL_KEYS",
    "EDIR",
    "EOPREG",
    "MIN_MARGIN",
    "SYSTEM_KEYS",
    "DipoleWindow",
    "dipole_window",
    "flips_c",
    "has_dipole",
    "is_true",
    "put_field",
    "ramp_margin",
    "remove_field",
    "short_margin",
]

EOPREG = 0.1  # pw.x's default width of the ramp, a fraction of the axis
MIN_MARGIN = 3.0  # Å: closer to an atom, its valence density reaches the ramp
EDIR = 3  # the vacuum of the surface types is along c: the direction a field starts with
CONTROL_KEYS = ("tefield", "dipfield")
SYSTEM_KEYS = ("edir", "emaxpos", "eopreg", "eamp")
DIGITS = 4
TRUE = frozenset({".true.", ".t.", "t"})


@dataclass(frozen=True)
class DipoleWindow:
    emaxpos: float  # fraction of the axis where the ramp starts
    eopreg: float  # fraction of the axis the ramp spans
    ramp: float  # Å, the ramp's width along the normal
    gap: float  # Å, the widest empty gap along the axis
    margin: float  # Å, from either end of the ramp to the nearest atom (0: an atom inside it)


def ramp_margin(heights: np.ndarray, emaxpos: float, eopreg: float) -> float:
    """From the ramp ``[emaxpos, emaxpos + eopreg]`` (wrapped into the cell) to the nearest of
    ``heights``, as a fraction of the axis: 0 with an atom inside the ramp."""
    values = np.asarray(heights, float).ravel()
    if values.size == 0:
        return max(0.0, 1.0 - eopreg) / 2.0
    after = (values - emaxpos) % 1.0  # 0 at the ramp's start
    if bool(np.any(after <= eopreg)):
        return 0.0
    return float(np.minimum(after - eopreg, 1.0 - after).min())


def dipole_window(
    cell: np.ndarray,
    frac: np.ndarray,
    axis: int = EDIR - 1,
    emaxpos: float | None = None,
    eopreg: float | None = None,
) -> DipoleWindow:
    """The ramp along ``axis``. A value given is the user's and is kept; one left out is computed:
    ``eopreg`` is pw.x's 0.1 when a third of the widest empty gap holds it, a third of the gap
    otherwise, and ``emaxpos`` puts the ramp in the middle of that gap."""
    spacing = float(interplanar(np.asarray(cell, float))[axis])
    heights = np.asarray(frac, float).reshape(-1, 3)[:, axis]
    start, width = widest_gap(heights)
    typed = emaxpos is not None or eopreg is not None
    if eopreg is None:
        eopreg = round(min(EOPREG, width / 3.0), DIGITS)
    if emaxpos is None:
        emaxpos = round((start + width / 2.0 - eopreg / 2.0) % 1.0, DIGITS)
        if emaxpos <= 0.0 or emaxpos >= 1.0:  # INPUT_PW: 0 < emaxpos < 1
            emaxpos = 10.0**-DIGITS
    margin = ramp_margin(heights, emaxpos, eopreg) if typed else (width - eopreg) / 2.0
    return DipoleWindow(
        emaxpos=emaxpos,
        eopreg=eopreg,
        ramp=eopreg * spacing,
        gap=width * spacing,
        margin=margin * spacing,
    )


def short_margin(window: DipoleWindow) -> bool:
    return window.margin < MIN_MARGIN


def is_true(text: str | None) -> bool:
    """A Fortran logical that reads as true (``.true.``, ``.T.``, ``t``)."""
    return text is not None and text.strip().lower() in TRUE


def has_dipole(value: Callable[[str, str], str | None]) -> bool:
    """Whether an input writes the dipole correction: ``tefield`` and ``dipfield`` both true.
    ``value`` is ``ScfInfo.value`` or ``InputEditor.get``."""
    return all(is_true(value("control", key)) for key in CONTROL_KEYS)


def _switch_off(editor: InputEditor, key: str) -> bool:
    """Take a logical of ``&CONTROL`` out when it is on; one written as false stays as it is."""
    return is_true(editor.get("control", key)) and editor.remove("control", key)


def put_field(
    editor: InputEditor,
    window: DipoleWindow,
    *,
    edir: int = EDIR,
    eamp: float = 0.0,
    dipfield: bool = True,
) -> tuple[str, ...]:
    """Write the saw-like field with ``window`` and, with ``dipfield``, the dipole correction;
    returns the keys taken out (a ``dipfield`` the text had, without it)."""
    if not is_true(editor.get("control", "tefield")):
        editor.set("control", "tefield", ".true.")
    removed: tuple[str, ...] = ()
    if not dipfield:
        removed = ("dipfield",) if _switch_off(editor, "dipfield") else ()
    elif not is_true(editor.get("control", "dipfield")):
        editor.set("control", "dipfield", ".true.")
    put_number(editor, "system", "edir", edir)
    put_number(editor, "system", "emaxpos", window.emaxpos)
    put_number(editor, "system", "eopreg", window.eopreg)
    put_number(editor, "system", "eamp", eamp)
    return removed


def remove_field(editor: InputEditor, *, dipfield: bool = True) -> tuple[str, ...]:
    """Take the field out of ``editor`` (``tefield`` and its four keys) and, with ``dipfield``, the
    correction's key too; returns the keys removed."""
    removed = ["dipfield"] if dipfield and _switch_off(editor, "dipfield") else []
    if _switch_off(editor, "tefield"):
        removed.append("tefield")
    removed += [key for key in SYSTEM_KEYS if editor.remove("system", key)]
    return tuple(removed)


def flips_c(
    cell: np.ndarray, frac: np.ndarray, labels: Sequence[str], symprec: float = 1e-3
) -> bool:
    """Whether a symmetry of the structure turns c upside down (a rotation whose third row is
    ``(0, 0, -1)``): such a slab has no dipole along c. Species are told apart by label, as pw.x
    does; False when spglib finds nothing."""
    import spglib

    kinds = {label: number for number, label in enumerate(dict.fromkeys(labels), 1)}
    structure = (
        np.asarray(cell, float).tolist(),
        np.asarray(frac, float).tolist(),
        [kinds[label] for label in labels],
    )
    try:
        with warnings.catch_warnings():  # 2.x warns about its error handling at every call
            warnings.simplefilter("ignore", DeprecationWarning)
            symmetry = spglib.get_symmetry(structure, symprec=symprec)
    except spglib.SpglibError:
        return False
    if not symmetry:
        return False
    return any(
        tuple(int(v) for v in rotation[2]) == (0, 0, -1) for rotation in symmetry["rotations"]
    )
