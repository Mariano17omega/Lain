"""The view of a 3D window as ``view3d.plot`` keeps it (spec 47 R1.2): the display options and the camera.

``session_of`` turns a window's state into plain YAML data; ``apply_options`` and ``camera_from_stored``
read it back. Reading never raises: a hand-edited or outdated value only drops itself (the spirit of
``plot_file.apply_stored``), and a camera with any bad number is dropped whole, so the view is framed as
in a window without a session. Species go by **label**, never by index: the index is the order of
``ATOMIC_SPECIES``, which may change while the colors should not.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from .camera import Camera
from .model import Structure
from .options import (
    BACKGROUNDS,
    LABEL_MODES,
    MAX_AXIS_WIDTH,
    MAX_FACTOR,
    MAX_LABEL_SIZE,
    MAX_RADIUS,
    MAX_REPEAT,
    MIN_AXIS_WIDTH,
    MIN_FACTOR,
    MIN_LABEL_SIZE,
    MIN_RADIUS,
    MIN_REPEAT,
    STYLES,
    DisplayOptions,
)

__all__ = ["CameraState", "apply_options", "camera_from_stored", "session_of"]

log = logging.getLogger(__name__)

ORTHONORMAL_TOL = 1e-6
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_INVALID = object()  # what a validator returns for a value it refuses


@dataclass(frozen=True)
class CameraState:
    """What of the camera is saved: rotation (rows), zoom (px per Å), pan (px) and focal (Å). The
    center is not: it is always the middle of the repeated block, which the options give."""

    rotation: tuple[tuple[float, ...], ...]  # 3 × 3
    zoom: float
    pan: tuple[float, float]
    focal: float

    @classmethod
    def of(cls, camera: Camera) -> CameraState:
        rotation = tuple(tuple(float(v) for v in row) for row in np.asarray(camera.rotation))
        pan = np.asarray(camera.pan, dtype=float)
        return cls(
            rotation, float(camera.zoom), (float(pan[0]), float(pan[1])), float(camera.focal)
        )

    def apply(self, camera: Camera) -> None:
        camera.rotation = np.array(self.rotation, dtype=float)
        camera.zoom = self.zoom
        camera.pan = np.array(self.pan, dtype=float)
        camera.focal = self.focal


# -- writing ------------------------------------------------------------------------------------------


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(int(c) for c in rgb))


def _options_data(structure: Structure, options: DisplayOptions) -> dict[str, Any]:
    labels = [species.label for species in structure.species]
    data: dict[str, Any] = {}
    for f in fields(options):
        value = getattr(options, f.name)
        if f.name == "reps":
            value = [int(n) for n in value]
        elif f.name == "species_colors":
            value = {labels[i]: _hex(value[i]) for i in range(len(labels)) if i in value}
        elif f.name == "species_hidden":
            value = [labels[i] for i in range(len(labels)) if i in value]
        elif isinstance(value, bool | str):
            pass
        elif isinstance(value, int):
            value = int(value)
        elif isinstance(value, float):
            value = float(value)
        data[f.name] = value
    return data


def session_of(
    structure: Structure, options: DisplayOptions, camera: CameraState | None
) -> dict[str, Any]:
    """The section of one file: ``options`` and, when the view was framed, ``camera``; plain Python
    values only (``yaml.safe_dump`` refuses numpy scalars)."""
    session: dict[str, Any] = {"options": _options_data(structure, options)}
    if camera is not None:
        session["camera"] = {
            "rotation": [list(row) for row in camera.rotation],
            "zoom": camera.zoom,
            "pan": list(camera.pan),
            "focal": camera.focal,
        }
    return session


# -- reading ------------------------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    """A finite number from YAML (``int`` or ``float``, never a ``bool``), else None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:  # an int beyond a float
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any, low: int, high: int) -> int | None:
    return value if type(value) is int and low <= value <= high else None


def _choice(choices: dict[str, str]) -> Callable[[Any, Structure], Any]:
    return lambda value, _s: value if isinstance(value, str) and value in choices else _INVALID


def _ranged(low: float, high: float) -> Callable[[Any, Structure], Any]:
    def check(value: Any, _s: Structure) -> Any:
        number = _number(value)
        return number if number is not None and low <= number <= high else _INVALID

    return check


def _flag(value: Any, _s: Structure) -> Any:
    return value if isinstance(value, bool) else _INVALID


def _label_size(value: Any, _s: Structure) -> Any:
    size = _integer(value, MIN_LABEL_SIZE, MAX_LABEL_SIZE)
    return _INVALID if size is None else size


def _reps(value: Any, _s: Structure) -> Any:
    if not isinstance(value, list) or len(value) != 3:
        return _INVALID
    counts = [_integer(n, MIN_REPEAT, MAX_REPEAT) for n in value]
    if any(n is None for n in counts):
        return _INVALID
    return tuple(counts)


def _indices(structure: Structure) -> dict[str, list[int]]:
    """Label → the species indices with it (a label repeated in ATOMIC_SPECIES names all of them)."""
    indices: dict[str, list[int]] = {}
    for index, species in enumerate(structure.species):
        indices.setdefault(species.label, []).append(index)
    return indices


def _species_colors(value: Any, structure: Structure) -> Any:
    if not isinstance(value, dict):
        return _INVALID
    known = _indices(structure)
    colors: dict[int, tuple[int, int, int]] = {}
    for label, color in value.items():
        if not isinstance(label, str) or label not in known:
            return _INVALID
        if not isinstance(color, str) or not _HEX.fullmatch(color):
            return _INVALID
        rgb = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
        for index in known[label]:
            colors[index] = rgb
    return colors


def _species_hidden(value: Any, structure: Structure) -> Any:
    if not isinstance(value, list):
        return _INVALID
    known = _indices(structure)
    if not all(isinstance(label, str) and label in known for label in value):
        return _INVALID
    return {index for label in value for index in known[label]}


_FIELDS: dict[str, Callable[[Any, Structure], Any]] = {
    "style": _choice(STYLES),
    "radius_scale": _ranged(MIN_RADIUS, MAX_RADIUS),
    "bond_factor": _ranged(MIN_FACTOR, MAX_FACTOR),
    "show_bonds": _flag,
    "reps": _reps,
    "labels": _choice(LABEL_MODES),
    "label_size": _label_size,
    "show_cell": _flag,
    "show_abc": _flag,
    "show_xyz": _flag,
    "abc_width": _ranged(MIN_AXIS_WIDTH, MAX_AXIS_WIDTH),
    "xyz_width": _ranged(MIN_AXIS_WIDTH, MAX_AXIS_WIDTH),
    "perspective": _flag,
    "background": _choice(BACKGROUNDS),
    "species_colors": _species_colors,
    "species_hidden": _species_hidden,
}


def apply_options(options: DisplayOptions, stored: Any, structure: Structure) -> list[str]:
    """Set the valid stored values on ``options``; the names of the ones ignored. Never raises: a field
    missing keeps the window's default, an unknown key is skipped."""
    if not isinstance(stored, dict):
        return ["options"]
    ignored: list[str] = []
    for name, value in stored.items():
        check = _FIELDS.get(name) if isinstance(name, str) else None
        if check is None:
            log.debug("view3d.plot: unknown option %r ignored", name)
            continue
        accepted = check(value, structure)
        if accepted is _INVALID:
            ignored.append(name)
            continue
        setattr(options, name, accepted)
    return ignored


def _rotation(value: Any) -> np.ndarray | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    rows = []
    for row in value:
        if not isinstance(row, list) or len(row) != 3:
            return None
        numbers = [_number(v) for v in row]
        if any(n is None for n in numbers):
            return None
        rows.append(numbers)
    matrix = np.array(rows, dtype=float)
    if not np.allclose(matrix @ matrix.T, np.eye(3), atol=ORTHONORMAL_TOL, rtol=0.0):
        return None
    return matrix if np.linalg.det(matrix) > 0 else None  # a mirror is no rotation


def camera_from_stored(data: Any) -> CameraState | None:
    """The saved camera, or None when anything of it is wrong (the view is then framed afresh)."""
    if not isinstance(data, dict):
        return None
    rotation = _rotation(data.get("rotation"))
    zoom, focal = _number(data.get("zoom")), _number(data.get("focal"))
    pan = data.get("pan")
    if not isinstance(pan, list) or len(pan) != 2:
        return None
    pan_xy = [_number(v) for v in pan]
    if rotation is None or zoom is None or focal is None or zoom <= 0 or focal <= 0:
        return None
    if pan_xy[0] is None or pan_xy[1] is None:
        return None
    return CameraState(
        tuple(tuple(float(v) for v in row) for row in rotation),
        zoom,
        (pan_xy[0], pan_xy[1]),
        focal,
    )
