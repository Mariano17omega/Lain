"""Temporary notice in the window's bottom right corner (spec 17 R3.4).

A child of the window, never a top-level one, so moving the window carries it along; an event
filter on the window places it again on resize and show, and stops it when the window closes.
One notice at a time from a queue: a 3 px countdown bar runs out (the animation is the timer,
paused while the mouse is over it), then the notice fades out and the next one comes. A click
closes it at once.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    pyqtProperty,  # pyright: ignore[reportAttributeAccessIssue]  (missing from the stubs)
    pyqtSignal,
)
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..dialogs.details import DetailsDialog, show_details
from ..theme.manager import ThemeManager

TOAST_MS = 6000
FADE_MS = 300
MARGIN = 16
WIDTH = 380
BAR_HEIGHT = 3
ICON_PX = 18
# level → (icon, color token)
LEVELS = {
    "info": ("info", "accent"),
    "success": ("check_circle", "success"),
    "warning": ("warning", "warning"),
}


def toast_width(parent_width: int, width: int, margin: int) -> int:
    """``width``, narrowed to what the parent has inside its margins."""
    return max(0, min(width, parent_width - 2 * margin))


def toast_position(
    parent_size: QSize, toast_size: QSize, margin: int, footer_height: int
) -> QPoint:
    """Top left corner of a toast in the parent's bottom right corner, above its footer."""
    width = toast_width(parent_size.width(), toast_size.width(), margin)
    x = max(0, parent_size.width() - margin - width)
    y = max(0, parent_size.height() - footer_height - margin - toast_size.height())
    return QPoint(x, y)


@dataclass(frozen=True)
class Notice:
    text: str
    level: str = "info"
    details: str = ""  # shown by "Detalhes" (no button without it)


class Countdown(QWidget):
    """The bar along the toast's bottom edge: the fraction of its time still left."""

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.token = "accent"
        self._fraction = 1.0
        self.setFixedHeight(BAR_HEIGHT)

    def _get_fraction(self) -> float:
        return self._fraction

    def _set_fraction(self, value: float) -> None:
        self._fraction = value
        self.update()

    fraction = pyqtProperty(float, _get_fraction, _set_fraction)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(0, 0, round(self.width() * self._fraction), self.height(), self.color())
        painter.end()

    def color(self):
        return self.theme.color(self.token)


class Toast(QFrame):
    shown = pyqtSignal(str)  # text of the notice now on screen
    expired = pyqtSignal()  # its time ran out: the fade starts
    closed = pyqtSignal()  # gone (faded, clicked or "Detalhes")

    def __init__(
        self,
        theme: ThemeManager,
        parent: QWidget,
        footer: QWidget | None = None,
        duration_ms: int = TOAST_MS,
        fade_ms: int = FADE_MS,
    ):
        super().__init__(parent)
        self.setObjectName("toast")
        self.theme, self.footer = theme, footer
        self.duration_ms, self.fade_ms = duration_ms, fade_ms
        self.current: Notice | None = None
        self.details_dialog: DetailsDialog | None = None
        self._queue: deque[Notice] = deque()
        self._parent: QWidget | None = parent

        self.icon = QLabel()
        self.icon.setFixedSize(ICON_PX, ICON_PX)
        self.text = QLabel()
        self.text.setObjectName("toastText")
        self.text.setWordWrap(True)
        self.details_button = QPushButton("Detalhes")
        self.details_button.setObjectName("toastAction")
        self.details_button.clicked.connect(self.open_details)
        self.countdown = Countdown(theme)
        row = QHBoxLayout()
        row.setContentsMargins(12, 10, 10, 8)
        row.setSpacing(10)
        row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.text, 1)
        row.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 0, 1, 1)
        layout.setSpacing(0)
        layout.addLayout(row)
        layout.addWidget(self.countdown)

        # The effect only runs while fading: an opacity effect renders through a pixmap.
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setEnabled(False)
        self.setGraphicsEffect(self._effect)
        self.countdown_animation = QPropertyAnimation(self.countdown, b"fraction", self)
        self.countdown_animation.setStartValue(1.0)
        self.countdown_animation.setEndValue(0.0)
        self.countdown_animation.finished.connect(self._fade_out)
        self.fade_animation = QPropertyAnimation(self._effect, b"opacity", self)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(self._close_current)
        theme.theme_changed.connect(self._on_theme_changed)
        parent.installEventFilter(self)
        self.hide()

    # -- public API -------------------------------------------------------------------------------
    def show_message(self, text: str, level: str = "info", details: str = "") -> None:
        """Queue a notice; it shows now if none is on screen."""
        if self._parent is None:  # the window closed
            return
        self._queue.append(Notice(text, level if level in LEVELS else "info", details))
        if self.current is None:
            self._show_next()

    def dismiss(self) -> None:
        """Close the notice on screen at once (no fade); the next one follows."""
        if self.current is None:
            return
        self.countdown_animation.stop()
        self.fade_animation.stop()
        self._close_current()

    def pause(self) -> None:
        if self.countdown_animation.state() == QAbstractAnimation.State.Running:
            self.countdown_animation.pause()

    def resume(self) -> None:
        if self.countdown_animation.state() == QAbstractAnimation.State.Paused:
            self.countdown_animation.resume()

    def open_details(self) -> None:
        notice = self.current
        if notice is None or not notice.details:
            return
        self.details_dialog = show_details(self.parentWidget(), "Detalhes", notice.details)
        self.dismiss()

    def shutdown(self) -> None:
        """The window is closing: nothing may run or show afterwards."""
        self._queue.clear()
        self.countdown_animation.stop()
        self.fade_animation.stop()
        self.current = None
        self.hide()
        if self._parent is not None:
            self._parent.removeEventFilter(self)
            self._parent = None

    # -- events -----------------------------------------------------------------------------------
    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if watched is self._parent and event is not None:
            kind = event.type()
            if kind in (QEvent.Type.Resize, QEvent.Type.Show) and self.current is not None:
                self.place()
            elif kind == QEvent.Type.Close:
                self.shutdown()
        return False

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.pause()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.resume()

    def mousePressEvent(self, event) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.dismiss()
            return
        super().mousePressEvent(event)

    # -- internals --------------------------------------------------------------------------------
    def place(self) -> None:
        """Bottom right corner of the parent, above its footer, narrowed to fit."""
        parent = self.parentWidget()
        if parent is None:
            return
        width = toast_width(parent.width(), WIDTH, MARGIN)
        self.setFixedWidth(width)
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth():
            height = layout.totalHeightForWidth(width)
        else:
            height = self.sizeHint().height()
        self.setFixedHeight(height)
        footer = self.footer
        footer_height = footer.height() if footer is not None and footer.isVisible() else 0
        self.move(toast_position(parent.size(), QSize(width, height), MARGIN, footer_height))
        self.raise_()

    def _show_next(self) -> None:
        if not self._queue:
            self.current = None
            return
        notice = self.current = self._queue.popleft()
        self.text.setText(notice.text)
        self.details_button.setVisible(bool(notice.details))
        self.setProperty("level", notice.level)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self._paint_level()
        self._effect.setEnabled(False)
        self._effect.setOpacity(1.0)
        self.countdown.fraction = 1.0
        self.show()
        self.place()
        self.countdown_animation.setDuration(max(1, self.duration_ms))
        self.countdown_animation.start()
        self.shown.emit(notice.text)

    def _fade_out(self) -> None:
        self.expired.emit()
        if self.fade_ms <= 0:
            self._close_current()
            return
        self._effect.setEnabled(True)
        self.fade_animation.setDuration(self.fade_ms)
        self.fade_animation.start()

    def _close_current(self) -> None:
        self.hide()
        self._effect.setEnabled(False)
        self.current = None
        self.closed.emit()
        self._show_next()

    def _paint_level(self) -> None:
        level = self.current.level if self.current is not None else "info"
        icon, token = LEVELS[level]
        self.icon.setPixmap(self.theme.pixmap(icon, token, ICON_PX))
        self.countdown.token = token
        self.countdown.update()

    def _on_theme_changed(self, _name: str) -> None:
        self._paint_level()
