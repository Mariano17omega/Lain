"""The cards (grid) and rows (list) of the file view, painted by hand (PRD §2.1.3).

Sizes come from the font metrics, so ``ui.font_scale`` never clips a name (spec 19 R2.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip

from ...core.file_kinds import human_size, status_label
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
ROW = 26


def name_font_for(selected: bool) -> QFont:
    return mono_font(12, QFont.Weight.Bold if selected else QFont.Weight.Normal)


def name_height() -> int:
    return max(16, QFontMetrics(name_font_for(True)).height())


def meta_height() -> int:
    return max(14, QFontMetrics(mono_font(10)).height() + 1)


def meta_band() -> int:
    """Height of the card's bottom strip that holds the state line (tooltip hit-test)."""
    return meta_height() + 12


def card_size() -> QSize:
    height = CARD_INSET + TILE_TOP + TILE + NAME_GAP + name_height() + 1 + meta_height()
    return QSize(scaled(CARD_WIDTH), height + CARD_BOTTOM)


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
            return card_size() - QSize(6, 6)
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
            meta, meta_token = "pasta acima", "text_meta"
        else:
            title = path.name
            icon_name, token = file_visual(path, is_dir)
            meta, meta_token = self._meta(path, is_dir, proxy.fs.size(proxy.mapToSource(index)))
            if proxy.is_pending(index):  # a badge filter waits for this folder's detection
                meta, meta_token = "detectando…", "text_meta"
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
            name_rect = QRect(
                int(rect.left()) + 6,
                int(tile.bottom()) + NAME_GAP,
                int(rect.width()) - 12,
                name_height(),
            )
            name = painter.fontMetrics().elidedText(
                title, Qt.TextElideMode.ElideMiddle, name_rect.width()
            )
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, name)
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
            name_rect = rect.toRect().adjusted(28, 0, -meta_width - 8, 0)
            name = painter.fontMetrics().elidedText(
                title, Qt.TextElideMode.ElideMiddle, name_rect.width()
            )
            painter.drawText(
                name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name
            )
        painter.restore()

    def _meta(self, path: Path, is_dir: bool, size: int) -> tuple[str, str]:
        """Folders: entry count. Files: state only on cards, size (and state) in list mode."""
        if is_dir:
            count = self.panel.item_count(path)
            return (f"{count} itens" if count is not None else "pasta"), "text_meta"
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
        if proxy.is_dir(index):
            return folder_tooltip(service, path)
        size = proxy.fs.size(proxy.mapToSource(index))
        meta = self._meta(path, False, size)[0]
        if self.panel.grid_mode:  # the state is the line under the name
            in_meta = pos.y() >= rect.bottom() - meta_band()
        else:  # the state ends the row
            in_meta = (
                pos.x() >= rect.right() - QFontMetrics(mono_font(10)).horizontalAdvance(meta) - 16
            )
        return state_tooltip(service, path, size) if in_meta else ""
