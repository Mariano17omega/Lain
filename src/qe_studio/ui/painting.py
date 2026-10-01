"""Small painting helpers shared by custom delegates."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen

from .theme.manager import ThemeManager

BADGE_FALLBACK = "other"  # token family for modules without (or with an unthemed) badge_token


def mono_font(pixel_size: int = 11, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("JetBrains Mono")
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def ui_font(pixel_size: int = 12, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Inter")
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def badge_width(text: str) -> int:
    return QFontMetrics(mono_font(9, QFont.Weight.Medium)).horizontalAdvance(text) + 8


def paint_badge(
    painter: QPainter,
    right: float,
    center_y: float,
    text: str,
    theme: ThemeManager,
    token: str | None = None,
) -> float:
    """Draw a heuristic tag (BANDS, PDOS…) ending at ``right``; returns its left edge.

    ``token`` selects the theme colors ``badge_<token>_{bg,fg,border}`` (the module's
    ``badge_token``); without one, or without those tokens in the theme, the generic ones.
    """
    kind = token if token and theme.has_color(f"badge_{token}_bg") else BADGE_FALLBACK
    width = badge_width(text)
    rect = QRectF(right - width, center_y - 7, width, 14)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(theme.color(f"badge_{kind}_border"), 1))
    painter.setBrush(theme.color(f"badge_{kind}_bg"))
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
    painter.setPen(theme.color(f"badge_{kind}_fg"))
    painter.setFont(mono_font(9, QFont.Weight.Medium))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()
    return rect.left()
