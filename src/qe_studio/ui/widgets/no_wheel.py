"""Spin boxes and combo boxes the mouse wheel never changes (spec 32 R2).

In a scrolled panel the wheel must scroll the panel: a field under the cursor that takes it changes
its value instead. These ignore the wheel (``event.ignore()`` hands it to the parent, the scroll
area) and take no focus from it (``StrongFocus``: Tab and click still focus them; the default
``WheelFocus`` focused them on a wheel turn, after which Up / Down changed the value).

Reusable: a field in any scrolled form takes ``NoWheelSpinBox``, ``NoWheelDoubleSpinBox`` or
``NoWheelComboBox`` instead of the Qt class.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class NoWheelSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None:
            event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
