"""Color math without Qt: WCAG 2 contrast and compositing of translucent theme colors."""

from __future__ import annotations

import re

from matplotlib.colors import to_hex, to_rgb

RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")


def relative_luminance(color: str) -> float:
    """WCAG 2 relative luminance (0 = black, 1 = white)."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    high, low = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def composite(color: str, background: str) -> str:
    """``color`` over the opaque ``background`` as ``#rrggbb`` (``rgba(...)`` or any CSS color)."""
    match = RGBA.fullmatch(color.strip())
    if match is None:
        return to_hex(color)
    red, green, blue, alpha = int(match[1]), int(match[2]), int(match[3]), float(match[4])
    below = [round(c * 255) for c in to_rgb(background)]
    mixed = [
        round(top * alpha + under * (1 - alpha))
        for top, under in zip((red, green, blue), below, strict=True)
    ]
    return "#{:02x}{:02x}{:02x}".format(*mixed)
