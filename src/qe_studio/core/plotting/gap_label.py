"""The legend entry of the energy gap (spec 20): its text and the invisible handle that carries it."""

from __future__ import annotations

from matplotlib.lines import Line2D

SYMBOL = {"up": "↑", "down": "↓", "global": "global"}


def gap_label(value: float, channel: str | None = None, approx: bool = False) -> str:
    """``$E_{gap}$ = 1.234 eV``; ``channel`` (``up`` | ``down`` | ``global``) is named before the sign.

    ``approx`` marks a gap read off a DOS curve: ``≈`` and two decimals, which is what the energy
    grid resolves.
    """
    name = "$E_{gap}$" if channel is None else f"$E_{{gap}}$ {SYMBOL[channel]}"
    if approx:
        return f"{name} ≈ {value:.2f} eV"
    return f"{name} = {value:.3f} eV"


def gap_handle(text: str) -> Line2D:
    """A legend entry that is only text: no line, no marker."""
    return Line2D([], [], linestyle="none", label=text)
