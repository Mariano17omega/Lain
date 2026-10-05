"""How many bytes of array data an object keeps alive (spec 27-4 R2).

Generic on purpose: no dataset needs code of its own. The dataset cache uses it to stay inside a
memory budget, so only the numpy arrays count (they are what is big); everything else is 0.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

MAX_DEPTH = 8


def nbytes_of(obj: Any) -> int:
    """Sum of ``ndarray.nbytes`` found by walking dataclasses, tuples, lists, sets and dicts.

    A view counts through its root array (which it keeps alive), once however many views share
    it. Depth is limited and visited containers are remembered, so cycles end.
    """
    seen: set[int] = set()
    return _walk(obj, seen, 0)


def _walk(obj: Any, seen: set[int], depth: int) -> int:
    if obj is None or depth > MAX_DEPTH:
        return 0
    if isinstance(obj, np.ndarray):
        root = obj
        while isinstance(root.base, np.ndarray):
            root = root.base
        if id(root) in seen:
            return 0
        seen.add(id(root))
        return int(root.nbytes)
    if isinstance(obj, str | bytes | int | float | bool):
        return 0
    if id(obj) in seen:
        return 0
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        seen.add(id(obj))
        return sum(
            _walk(getattr(obj, f.name, None), seen, depth + 1) for f in dataclasses.fields(obj)
        )
    if isinstance(obj, dict):
        seen.add(id(obj))
        return sum(_walk(v, seen, depth + 1) for v in obj.values())
    if isinstance(obj, tuple | list | set | frozenset):
        seen.add(id(obj))
        return sum(_walk(item, seen, depth + 1) for item in obj)
    return 0
