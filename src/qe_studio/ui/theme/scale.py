"""The font scale in force, for code that has no ``ThemeManager`` at hand (paint helpers).

``ThemeManager`` owns it (``ui.font_scale``) and calls :func:`set_current`; delegates and widgets
size their fonts and text-holding heights through :func:`scaled_font` / :func:`scaled`.
"""

from __future__ import annotations

from ...core.fontscale import MIN_FONT_PX, clamp_scale, scale_px

_scale = 1.0


def current() -> float:
    return _scale


def set_current(scale: float) -> None:
    global _scale
    _scale = clamp_scale(scale)


def scaled(px: float) -> int:
    """A height or width that holds text, at the current scale."""
    return scale_px(px, _scale)


def scaled_font(px: float) -> int:
    """A font pixel size at the current scale (never below ``MIN_FONT_PX``)."""
    return scale_px(px, _scale, MIN_FONT_PX)
