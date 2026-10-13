"""Small data holders shared by the painter renderer: stats, projection, primitive table."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class FrameStats:
    atoms: int = 0  # real atoms drawn
    ghosts: int = 0
    bonds: int = 0
    primitives: int = 0
    ms: float = 0.0
    draft: bool = False


@dataclass
class Projection:
    xy: np.ndarray
    depth: np.ndarray
    scale: np.ndarray
    visible: np.ndarray  # finite position and species not hidden
    radius_px: np.ndarray
    has_spheres: bool


@dataclass
class Prims:
    """Struct-of-arrays of primitives, filled block by block and concatenated once."""

    parts: dict[str, list[np.ndarray]] = field(
        default_factory=lambda: {
            k: [] for k in ("kind", "x1", "y1", "x2", "y2", "depth", "size", "spec", "ghost")
        }
    )

    def add(self, kind, p1, p2, depth, size, spec, ghost=None) -> None:
        n = len(p1)
        if n == 0:
            return
        parts = self.parts
        parts["kind"].append(np.full(n, kind, dtype=np.int8))
        parts["x1"].append(p1[:, 0])
        parts["y1"].append(p1[:, 1])
        parts["x2"].append(p2[:, 0])
        parts["y2"].append(p2[:, 1])
        parts["depth"].append(depth)
        parts["size"].append(np.broadcast_to(np.asarray(size, dtype=float), (n,)))
        parts["spec"].append(np.broadcast_to(np.asarray(spec), (n,)))
        parts["ghost"].append(np.zeros(n, bool) if ghost is None else ghost)

    def finish(self) -> dict[str, np.ndarray]:
        parts = self.parts
        if not parts["kind"]:
            return {k: np.zeros(0) for k in parts} | {"order": np.zeros(0, dtype=int)}
        out = {k: np.concatenate(v) for k, v in parts.items()}
        finite = np.isfinite(out["x1"] + out["y1"] + out["x2"] + out["y2"])
        order = np.argsort(-out["depth"], kind="stable")  # far to near: painter's algorithm
        out["order"] = order[finite[order]]
        return out
