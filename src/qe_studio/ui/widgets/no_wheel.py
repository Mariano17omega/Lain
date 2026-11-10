"""Spin boxes and combo boxes the mouse wheel never changes (spec 32 R2).

In a scrolled panel the wheel must scroll the panel: a field under the cursor that takes it changes
its value instead. These ignore the wheel (``event.ignore()`` hands it to the parent, the scroll
area) and take no focus from it (``StrongFocus``: Tab and click still focus them; the default
``WheelFocus`` focused them on a wheel turn, after which Up / Down changed the value).

Reusable: a field in any scrolled form takes ``NoWheelSpinBox``, ``NoWheelDoubleSpinBox`` or
``NoWheelComboBox`` instead of the Qt class.
"""

from __future__ import annotations

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QValidator, QWheelEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class NoWheelSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """A decimal **point** whatever the system locale, and a typed comma is read as a point
    (CLAUDE.md, "Numbers"): the C locale reads ``1,5`` as 15 (a group separator), so the comma is
    replaced before Qt sees the text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setLocale(QLocale.c())

    def validate(self, input: str | None, pos: int) -> tuple[QValidator.State, str, int]:  # noqa: A002
        return super().validate((input or "").replace(",", "."), pos)

    def valueFromText(self, text: str | None) -> float:  # noqa: N802
        return super().valueFromText((text or "").replace(",", "."))

    def fixup(self, input: str | None) -> str:  # noqa: A002
        return super().fixup((input or "").replace(",", "."))

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class NoWheelComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()
