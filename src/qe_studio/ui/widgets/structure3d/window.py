"""One "Visualização 3D" window (spec 43 R4.3): a top-level window without a parent (its own taskbar
entry, it may stay behind the main one), one per click, each with its own options, camera and current
atom. Nothing is saved: it opens with the defaults and the background of the app theme at that moment.

The window emits ``closed(self)`` from its ``closeEvent``, so whoever keeps it drops it there (never
through ``destroyed``).
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ....core.structure3d.elements import element_for_label
from ....core.structure3d.model import AtomRef, Structure, atom_name
from ....core.structure3d.options import DisplayOptions
from ...theme.manager import ThemeManager
from ..common import IconButton, set_variant
from .canvas import StructureCanvas
from .panel import StructurePanel

TITLE = "Visualização 3D"
PANEL_WIDTH = 320
SIZE = (1280, 820)
VIEWS = ("a", "b", "c", "x", "y", "z")


def window_title(structure: Structure) -> str:
    """``scf.in — Analise_1 · Visualização 3D``."""
    path = Path(structure.source.path or "input")
    return (
        f"{path.name} — {path.parent.name} · {TITLE}"
        if path.parent.name
        else f"{path.name} · {TITLE}"
    )


def status_text(structure: Structure) -> str:
    """``scf.in · CH18Al8HgO36Si8 · nat = 72 · ibrav = 0``."""
    source = structure.source
    name = Path(source.path).name if source.path else "input"
    return f"{name} · {structure.formula} · nat = {source.nat} · ibrav = {source.ibrav}"


class StructureWindow(QMainWindow):
    closed = pyqtSignal(object)  # this window, from closeEvent

    def __init__(
        self, structure: Structure, theme: ThemeManager, settings: QSettings | None = None
    ):
        super().__init__(None)  # top level on purpose: independent of the main window
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("structureWindow")
        self.structure = structure
        background = "claro" if theme.name == "light" else "escuro"
        self.canvas = StructureCanvas(theme, structure, DisplayOptions(background=background))
        self.panel = StructurePanel(theme, self.canvas, settings)

        view = QWidget()
        column = QVBoxLayout(view)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._bar(theme))
        column.addWidget(self.canvas, 1)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.panel)
        self.splitter.addWidget(view)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([PANEL_WIDTH, SIZE[0] - PANEL_WIDTH])
        self.setCentralWidget(self.splitter)
        self._status()
        self.canvas.hovered.connect(self._show_hover)
        self.setWindowTitle(window_title(structure))
        self.resize(*SIZE)
        self.canvas.setFocus()

    def _bar(self, theme: ThemeManager) -> QWidget:
        """Above the view, like a plot's: "Resetar vista" and the "Vista" menu."""
        bar = QWidget()
        bar.setObjectName("plotToolbar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        self.reset_button = IconButton(
            theme, "home", "Resetar vista (R)", "plotTool", "text_secondary", "accent", 15
        )
        self.reset_button.setText("Resetar vista")
        self.reset_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.reset_button.clicked.connect(self._reset_clicked)
        self.view_button = set_variant(QToolButton(), "plotTool")
        self.view_button.setText("Vista")
        self.view_button.setToolTip("Olhar ao longo de um eixo")
        self.view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.view_button)
        self.view_actions: dict[str, QAction] = {}
        for name in VIEWS:
            action = menu.addAction(f"Ao longo de {name} ({name.upper()})")
            assert action is not None
            action.triggered.connect(lambda _=False, n=name: self.canvas.view_along(n))
            self.view_actions[name] = action
        self.view_button.setMenu(menu)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.view_button)
        layout.addStretch(1)
        return bar

    def _reset_clicked(self) -> None:
        self.canvas.reset_view()

    def _status(self) -> None:
        bar = self.statusBar()
        assert bar is not None
        bar.setObjectName("structureStatus")
        self.info = set_variant(QLabel(status_text(self.structure)), "readout")
        self.hover = set_variant(QLabel(""), "readout")
        self.warning = set_variant(QLabel("⚠"), "warning")
        warnings = self.structure.source.warnings
        self.warning.setToolTip("\n".join(warnings))
        self.warning.setVisible(bool(warnings))
        bar.addWidget(self.info, 1)
        bar.addPermanentWidget(self.hover)
        bar.addPermanentWidget(self.warning)

    def _show_hover(self, ref: AtomRef | None) -> None:
        if ref is None:
            self.hover.setText("")
            return
        element = element_for_label(self.structure.labels[ref.index])
        self.hover.setText(f"{atom_name(self.structure, ref)} · {element.name}")

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802 (Qt naming)
        self.closed.emit(self)
        super().closeEvent(event)
