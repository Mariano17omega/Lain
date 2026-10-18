"""The cards (grid) and rows (list) of the file view, painted by hand (PRD §2.1.3).

Sizes come from the font metrics, so ``ui.font_scale`` never clips a name (spec 19 R2.3). A long
name wraps over several lines instead of eliding (spec 37 R1): the grid is uniform, so every card of
a folder is as tall as the longest name listed there (``FilePanel.name_lines``).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip

from ...core.file_kinds import human_size, status_label
from ...i18n import _, ngettext
from ..file_types import file_visual, level_token
from ..painting import mono_font
from ..theme.manager import ThemeManager
from ..theme.scale import scaled
from .item_tooltips import folder_tooltip, is_tooltip, state_tooltip

if TYPE_CHECKING:
    from .file_grid import FilePanel

# Card, at scale 1 (148 x 86): inset 2.5 around, tile 34 at 7 from the top, name 4 below it,
# meta 1 below the name, 5 of air at the bottom. The two text lines are as tall as their font.
CARD_WIDTH = 148
CARD_INSET = 5  # both sides of the painted rect together
TILE, TILE_TOP, NAME_GAP, CARD_BOTTOM = 34, 7, 4, 5
NAME_SIDE = 12  # air at both sides of the name, inside the painted rect
CARD_MARGIN = 6  # the item is the grid cell less this (``sizeHint``): the card's air in its cell
ROW = 26
MAX_NAME_LINES = 6  # about 108 characters at scale 1; only past it the last line ends in "…"
BREAK_AFTER = "-_. "  # a long name prefers to wrap after one of these, kept at its line's end


def name_font_for(selected: bool) -> QFont:
    return mono_font(12, QFont.Weight.Bold if selected else QFont.Weight.Normal)


def name_height() -> int:
    return max(16, QFontMetrics(name_font_for(True)).height())


def meta_height() -> int:
    return max(14, QFontMetrics(mono_font(10)).height() + 1)


def meta_band() -> int:
    """Height of the card's bottom strip that holds the state line (tooltip hit-test)."""
    return meta_height() + 12


def name_width() -> int:
    """Width of one line of a card's name: the item (the grid cell less ``CARD_MARGIN``), then
    the painted rect (``CARD_INSET`` in), less the air at its sides."""
    return scaled(CARD_WIDTH) - CARD_MARGIN - CARD_INSET - NAME_SIDE


def name_metrics() -> QFontMetrics:
    return QFontMetrics(name_font_for(True))  # a selected name is bold, the widest weight


def card_size(lines: int = 1) -> QSize:
    """The card for a name of ``lines`` lines (1 = today's 148 x 86 at scale 1)."""
    lines = min(max(lines, 1), MAX_NAME_LINES)
    height = CARD_INSET + TILE_TOP + TILE + NAME_GAP + lines * name_height() + 1 + meta_height()
    return QSize(scaled(CARD_WIDTH), height + CARD_BOTTOM)


def wrap_name(
    text: str, width: int, metrics: QFontMetrics, max_lines: int = MAX_NAME_LINES
) -> list[str]:
    """``text`` in lines that fit ``width`` px (spec 37 R1.1).

    A line breaks after the last ``BREAK_AFTER`` character that leaves it more than half full,
    else at the last character that fits (a word wider than the line cannot spill out of the
    card). Past ``max_lines`` the last line is elided on the right with "…". Pure over the
    metrics: no widget, no disk. Joined, the lines are ``text`` unless it was cut.
    """
    lines: list[str] = []
    rest = text
    while rest:
        total = metrics.horizontalAdvance(rest)
        if total <= width:
            lines.append(rest)
            break
        if len(lines) >= max_lines - 1:
            lines.append(metrics.elidedText(rest, Qt.TextElideMode.ElideRight, width))
            break
        fit = _chars_that_fit(rest, total, width, metrics)
        cut = next((k for k in range(fit, fit // 2, -1) if rest[k - 1] in BREAK_AFTER), fit)
        lines.append(rest[:cut])
        rest = rest[cut:]
    return lines or [""]


def _chars_that_fit(text: str, total: int, width: int, metrics: QFontMetrics) -> int:
    """Largest ``n`` (one at least, so every line makes progress) with ``text[:n]`` within
    ``width``; ``total`` is the advance of ``text`` (wider than ``width``). The guess by
    proportion is exact in the mono font, so a few measures settle it."""
    n = max(1, min(len(text) - 1, len(text) * width // total))
    if metrics.horizontalAdvance(text[:n]) <= width:
        while n < len(text) and metrics.horizontalAdvance(text[: n + 1]) <= width:
            n += 1
        return n
    n -= 1
    while n > 1 and metrics.horizontalAdvance(text[:n]) > width:
        n -= 1
    return n


def name_lines(names: Iterable[str], width: int, metrics: QFontMetrics) -> int:
    """Lines of the longest of ``names`` (1 when all fit one line), at most ``MAX_NAME_LINES``.
    Only a name wider than ``width`` is wrapped, so short ones cost a measure."""
    most = 1
    for name in names:
        if metrics.horizontalAdvance(name) > width:
            most = max(most, len(wrap_name(name, width, metrics)))
            if most >= MAX_NAME_LINES:
                break
    return most


def row_height() -> int:
    return max(scaled(ROW), QFontMetrics(name_font_for(True)).height() + 10)


class FileCardDelegate(QStyledItemDelegate):
    def __init__(self, panel: FilePanel):
        super().__init__()
        self.panel = panel

    @property
    def theme(self) -> ThemeManager:
        return self.panel.theme

    def sizeHint(self, option, index) -> QSize:
        if self.panel.grid_mode:
            return card_size(self.panel.name_lines) - QSize(CARD_MARGIN, CARD_MARGIN)
        return QSize(option.rect.width(), row_height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        proxy = self.panel.proxy
        path = proxy.path(index)
        is_dir = proxy.is_dir(index)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)  # current item, view focused
        theme = self.theme
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2.5, 2.5, -2.5, -2.5)
        if selected:
            background, border = theme.color("accent_soft"), theme.color("accent")
        elif hovered:
            background, border = theme.color("card_hover"), theme.color("border_strong")
        else:
            background, border = theme.color("card"), theme.color("border")
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 4, 4)
        if focused:  # the keyboard focus ring (spec 19 R4.2), inside the card
            painter.setPen(QPen(theme.color("focus_ring"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 3, 3)

        if proxy.is_up(index):  # the "folder above" shortcut (spec 5 R2)
            title = ".."
            icon_name, token = "drive_folder_upload", "icon_folder"
            meta, meta_token = _("pasta acima"), "text_meta"
        else:
            title = path.name
            icon_name, token = file_visual(path, is_dir)
            meta, meta_token = self._meta_for(index, path, is_dir)
        name_color = theme.color("accent_text" if selected or is_dir else "text")
        name_font = name_font_for(selected)
        if self.panel.grid_mode:
            tile = QRectF(rect.center().x() - TILE / 2, rect.top() + TILE_TOP, TILE, TILE)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.color("window"))
            painter.drawRoundedRect(tile, 4, 4)
            painter.drawPixmap(
                int(tile.center().x() - 10),
                int(tile.center().y() - 10),
                theme.pixmap(icon_name, token, 20),
            )
            painter.setFont(name_font)
            painter.setPen(name_color)
            room = self.panel.name_lines  # the lines every card of this folder has for its name
            name_rect = QRect(
                int(rect.left()) + NAME_SIDE // 2,
                int(tile.bottom()) + NAME_GAP,
                int(rect.width()) - NAME_SIDE,
                name_height() * room,
            )
            for row, line in enumerate(wrap_name(title, name_width(), name_metrics(), room)):
                line_rect = QRect(
                    name_rect.left(),
                    name_rect.top() + row * name_height(),
                    name_rect.width(),
                    name_height(),
                )
                painter.drawText(line_rect, Qt.AlignmentFlag.AlignCenter, line)
            painter.setFont(mono_font(10))
            painter.setPen(theme.color(meta_token))
            painter.drawText(
                QRect(int(rect.left()), name_rect.bottom() + 1, int(rect.width()), meta_height()),
                Qt.AlignmentFlag.AlignCenter,
                meta,
            )
        else:
            painter.drawPixmap(
                int(rect.left()) + 6, int(rect.center().y() - 8), theme.pixmap(icon_name, token, 16)
            )
            painter.setFont(mono_font(10))
            meta_width = painter.fontMetrics().horizontalAdvance(meta) + 8
            painter.setPen(theme.color(meta_token))
            painter.drawText(
                rect.toRect().adjusted(0, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                meta,
            )
            painter.setFont(name_font)
            painter.setPen(name_color)
            name_rect = self._list_name_rect(rect, meta_width)
            name = painter.fontMetrics().elidedText(
                title, Qt.TextElideMode.ElideMiddle, name_rect.width()
            )
            painter.drawText(
                name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name
            )
        painter.restore()

    @staticmethod
    def _list_name_rect(rect: QRectF, meta_width: int) -> QRect:
        """Where a row's name goes: after the icon, before the size / state at the right."""
        return rect.toRect().adjusted(28, 0, -meta_width - 8, 0)

    def _meta_for(self, index: QModelIndex, path: Path, is_dir: bool) -> tuple[str, str]:
        """The line under a card's name (or at the end of a row) and its color token."""
        proxy = self.panel.proxy
        if proxy.is_pending(index):  # a badge filter waits for this folder's detection
            return _("detectando…"), "text_meta"
        return self._meta(path, is_dir, proxy.fs.size(proxy.mapToSource(index)))

    def _meta(self, path: Path, is_dir: bool, size: int) -> tuple[str, str]:
        """Folders: entry count. Files: state only on cards, size (and state) in list mode."""
        if is_dir:
            count = self.panel.item_count(path)
            if count is None:
                return _("pasta"), "text_meta"
            return ngettext("{n} item", "{n} itens", count).format(n=count), "text_meta"
        label = status_label(path, size, self.panel.service.file_sniff(path))
        if label is None:
            return ("", "text_meta") if self.panel.grid_mode else (human_size(size), "text_meta")
        text, token = label[0], level_token(label[1])
        return (text, token) if self.panel.grid_mode else (f"{human_size(size)} · {text}", token)

    def helpEvent(self, event, view, option, index) -> bool:
        """Tooltips (spec 18 R3): a folder card explains its badges, a file its state label."""
        if event is None or view is None or not index.isValid():
            return super().helpEvent(event, view, option, index)
        text = self._tooltip_at(event.pos(), option.rect, index) if is_tooltip(event) else ""
        if not text:
            return super().helpEvent(event, view, option, index)
        QToolTip.showText(event.globalPos(), text, view.viewport(), option.rect)
        return True

    def _tooltip_at(self, pos: QPoint, rect: QRect, index: QModelIndex) -> str:
        proxy, service = self.panel.proxy, self.panel.service
        if proxy.is_up(index):
            return ""
        path = proxy.path(index)
        is_dir = proxy.is_dir(index)
        meta = self._meta_for(index, path, is_dir)[0]
        parts = [path.name if self._name_cut(path.name, rect, meta) else ""]  # spec 37 R1.3
        if is_dir:
            parts.append(folder_tooltip(service, path))
        else:
            if self.panel.grid_mode:  # the state is the line under the name
                in_meta = pos.y() >= rect.bottom() - meta_band()
            else:  # the state ends the row
                in_meta = (
                    pos.x()
                    >= rect.right() - QFontMetrics(mono_font(10)).horizontalAdvance(meta) - 16
                )
            if in_meta:
                size = proxy.fs.size(proxy.mapToSource(index))
                parts.append(state_tooltip(service, path, size))
        return "\n\n".join(part for part in parts if part)

    def _name_cut(self, name: str, rect: QRect, meta: str) -> bool:
        """Whether the card (or row) shows ``name`` incomplete: past the line limit, or elided
        in a row. Mirrors ``paint``, which wraps / elides with the same widths."""
        if self.panel.grid_mode:
            lines = wrap_name(name, name_width(), name_metrics(), self.panel.name_lines)
            return "".join(lines) != name
        meta_width = QFontMetrics(mono_font(10)).horizontalAdvance(meta) + 8
        shown = QRectF(rect).adjusted(2.5, 2.5, -2.5, -2.5)
        width = max(self._list_name_rect(shown, meta_width).width(), 0)
        return QFontMetrics(name_font_for(False)).horizontalAdvance(name) > width
