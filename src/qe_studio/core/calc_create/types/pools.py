"""The pools (``pw.x -nk``) of the script, chosen from NP and the k-points (spec 102).

The cluster's rules (Lucci, the ``physica`` environment): NP is 32, 64 or 128, ``-nk`` is a multiple of 4
and at most 16 (memory: each pool holds its own copy of the density), it divides NP exactly and keeps at
least 4 cores per pool (the manual's rule of thumb, ``K = N/4``). A single k-point (gamma) takes ``-nk 1``,
the only value pw.x accepts there.

The k-points that the pools share are the irreducible ones, which pw.x only knows once it has found the
symmetry. ``kpoint_count`` estimates them with spglib on the structure of each generated input (a slab
has other symmetry than its bulk); an LSDA run counts both spins, as ``divide_et_impera`` does with
``kunit = 1`` (QE 7.3, ``setup.f90``). The script runs every pw.x input with the same ``-nk``, so the
input with the fewest k-points decides.
"""

from __future__ import annotations

import functools
import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ...qe.input_edit import InputEditor
from ...qe.lattice import StructureError, crystal_from_editor
from ...qe.pw_input import fortran_int
from ..kpath import KMesh
from .base import PlannedFile

__all__ = [
    "MAX_POOLS",
    "MIN_CORES_PER_POOL",
    "POOL_BALANCE",
    "POOL_STEP",
    "Pools",
    "auto_pools",
    "kpoint_count",
    "planned_kpoints",
    "pool_choices",
]

POOL_STEP = 4  # nk is a multiple of it (the cluster administrator's rule)
MAX_POOLS = 16  # and at most this (memory)
MIN_CORES_PER_POOL = 4  # the manual's K = N/4
POOL_BALANCE = 0.8  # the share of the pools' time that is not idle at least
SYMPREC = 1e-3  # spglib's, as the rest of "Criar cálculo" (``surface/dipole.py``)


@dataclass(frozen=True)
class Pools:
    """The script's NP and nk, and what they came from."""

    np: int
    nk: int
    auto: bool  # nk was computed (the field was empty)
    nks: int | None  # the k-points estimated, None when no input says


def pool_choices(np_: int) -> list[int]:
    """The nk the cluster accepts for ``np_`` cores, ascending: multiples of 4 up to 16 that divide NP
    and leave 4 cores to each pool (NP = 32: 4, 8; NP = 64 or 128: 4, 8, 16)."""
    top = min(MAX_POOLS, np_ // MIN_CORES_PER_POOL)
    return [pools for pools in range(POOL_STEP, top + 1, POOL_STEP) if np_ % pools == 0]


def auto_pools(np_: int, nks: int | None) -> int:
    """The nk for ``np_`` cores and ``nks`` k-points (None: unknown).

    1 for a single k-point and when no multiple of 4 fits NP. Else the largest choice with no more
    pools than k-points whose pools are at least ``POOL_BALANCE`` busy (``nks`` spread over ``nk``
    pools takes ``ceil(nks / nk)`` rounds); when none is, the smallest one: the cluster does not accept
    less, and ``pool_notes`` says the pools that stay idle."""
    choices = pool_choices(np_)
    if nks == 1 or not choices:
        return 1
    if nks is None:
        return choices[-1]
    for pools in reversed(choices):
        if pools <= nks and nks / (pools * math.ceil(nks / pools)) >= POOL_BALANCE:
            return pools
    return choices[0]


def _irreducible(editor: InputEditor, mesh: KMesh) -> int:
    """The mesh's irreducible k-points for the structure of ``editor`` (spglib, with time reversal);
    the whole mesh when the structure cannot be read or spglib finds nothing: the upper bound."""
    try:
        crystal = crystal_from_editor(editor)
    except (StructureError, ValueError):
        return mesh.count
    import spglib

    kinds = {label: number for number, label in enumerate(dict.fromkeys(crystal.labels), 1)}
    structure = (
        np.asarray(crystal.cell, float).tolist(),
        np.asarray(crystal.frac, float).tolist(),
        [kinds[label] for label in crystal.labels],
    )
    try:
        with warnings.catch_warnings():  # 2.x warns about its error handling at every call
            warnings.simplefilter("ignore", DeprecationWarning)
            found = spglib.get_ir_reciprocal_mesh(
                list(mesh.n), structure, is_shift=list(mesh.shift), symprec=SYMPREC
            )
    except (spglib.SpglibError, ValueError):
        return mesh.count
    if found is None:  # it gives up on a structure it cannot make sense of
        return mesh.count
    return len(set(found[0].tolist()))


@functools.lru_cache(maxsize=32)
def kpoint_count(text: str) -> int | None:
    """The k-points of the pw.x input ``text`` that the pools share, None when it does not say: a band
    path (``*_b``, the points between the corners are generated) or a card it cannot read. A missing
    card is gamma, as ``gamma_pool_notes`` takes it. Cached on the text: ``plan`` runs on every edit."""
    editor = InputEditor.from_text(text)
    card = editor.card("K_POINTS")
    if card is None or card.option == "gamma":
        return 1  # pw.x refuses pools here, whatever the spin
    count: int | None
    if card.option == "automatic":
        mesh = KMesh.parse(card.lines[0]) if card.lines else None
        count = _irreducible(editor, mesh) if mesh is not None and not mesh.problems() else None
    elif card.option.endswith("_b"):
        count = None
    else:  # tpiba, crystal...: the first line is how many
        count = fortran_int(card.lines[0]) if card.lines else None
    if count is None:
        return None
    return count * 2 if fortran_int(editor.get("system", "nspin")) == 2 else count


def planned_kpoints(files: Sequence[PlannedFile]) -> int | None:
    """The fewest k-points among the pw.x inputs of ``files`` (None: none says)."""
    counts = [kpoint_count(planned.text) for planned in files if planned.kind == "pw_input"]
    known = [count for count in counts if count is not None and count > 0]
    return min(known) if known else None
