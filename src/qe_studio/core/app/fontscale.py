"""Font scale (``ui.font_scale``, spec 19 R2): pixel sizes and QSS text, without Qt.

Only fonts, and the heights that hold text, follow the scale; paddings, icons and dialog widths
do not.
"""

from __future__ import annotations

import re

MIN_SCALE = 0.8
MAX_SCALE = 1.6
MIN_FONT_PX = 8  # a smaller font is unreadable, whatever the scale
# Heights of QSS rules that would clip text on a bigger font: `${token}` → px at scale 1.
SIZE_BASE = {"row_h": 22, "bar_h": 30, "status_h": 22, "activity_w": 46}
_FONT_SIZE = re.compile(r"(font-size:\s*)(\d+)px")


def clamp_scale(scale: float) -> float:
    return min(MAX_SCALE, max(MIN_SCALE, float(scale)))


def scale_px(px: float, scale: float, minimum: int = 0) -> int:
    """``px`` times ``scale``, rounded to a whole pixel and not below ``minimum``."""
    return max(minimum, round(px * scale))


def scale_qss(text: str, scale: float) -> str:
    """Every ``font-size: Npx`` of ``text`` scaled (whole px, at least ``MIN_FONT_PX``)."""
    if scale == 1.0:
        return text
    return _FONT_SIZE.sub(lambda m: f"{m[1]}{scale_px(int(m[2]), scale, MIN_FONT_PX)}px", text)


def size_tokens(scale: float) -> dict[str, str]:
    """The QSS tokens of ``SIZE_BASE`` at ``scale`` (``row_h`` → ``"22px"``…)."""
    return {name: f"{scale_px(px, scale)}px" for name, px in SIZE_BASE.items()}
