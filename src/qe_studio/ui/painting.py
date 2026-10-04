"""Small painting helpers shared by custom delegates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen

from .theme.manager import ThemeManager

BADGE_FALLBACK = "other"  # token family for modules without (or with an unthemed) badge_token
BADGE_GAP = 4  # between two badges of one row
T = TypeVar("T")


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


def badge_rect(right: float, center_y: float, text: str) -> QRectF:
    """Where a badge of ``text`` ending at ``right`` is drawn."""
    width = badge_width(text)
    return QRectF(right - width, center_y - 7, width, 14)


def badge_layout(
    items: Sequence[tuple[str, T]], right: float, center_y: float
) -> list[tuple[QRectF, T]]:
    """Rects of a row of badges painted right to left (``items``: (text, payload), the first one
    is the rightmost). The same arithmetic as the paint loops, so a tooltip hit-test cannot drift."""
    placed = []
    for text, payload in items:
        rect = badge_rect(right, center_y, text)
        placed.append((rect, payload))
        right = rect.left() - BADGE_GAP
    return placed


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
    rect = badge_rect(right, center_y, text)
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
