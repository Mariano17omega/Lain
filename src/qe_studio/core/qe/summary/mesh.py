"""The k-point mesh of a pw.x output, from the input next to it (spec 33 R1).

pw.x prints the number of irreducible k points, never the mesh asked for: that is in the input
(``pw.x -i x.in > x.out``), so the one with the output's stem is read.
"""

from __future__ import annotations

from pathlib import Path

from ...sniff import INPUT_READ_LIMIT, looks_like_input
from ..input_extract import k_points_text
from ..input_lint import lint


def k_mesh_of(output: Path) -> str | None:
    """``automatic 5×5×5 (0 0 0)``, ``gamma``… as the input's ``K_POINTS`` chip says it; ``None``
    without a readable input of the same name or without that card. Never raises."""
    try:
        path = output.with_suffix(".in")
        if path == output or not looks_like_input(path):
            return None
        with open(path, "rb") as handle:
            text = handle.read(INPUT_READ_LIMIT).decode("utf-8", errors="replace")
        card = lint(text).card("K_POINTS")
    except (OSError, ValueError):
        return None
    return k_points_text(card) if card is not None else None
