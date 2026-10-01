"""Plot parameters panel (PRD §2.1.2 plot mode): one tuning body per open plot."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.calculations.base import Dataset
from ...core.calculations.params import CommonParams
from ..plot_session import PlotSession
from ..theme.manager import ThemeManager
from .common import IconButton, PanelHeader, set_variant
from .params_body import ParamsBody


class ParamsPanel(QWidget):
    """Header + a stack of per-session bodies, so switching tabs keeps each plot's widgets.

    A body is built the first time its session is bound and dropped by ``discard`` when the plot
    tab closes (or rebuilt by ``bind`` when its schema changed). Every body sits in its own scroll
    area, which keeps the scroll position too.
    """

    changed = pyqtSignal(str)  # parameter name
    back_requested = pyqtSignal()
    remap_requested = pyqtSignal()
    export_requested = pyqtSignal()
    generate_requested = pyqtSignal()
    restore_requested = pyqtSignal()

    def __init__(
        self,
        theme: ThemeManager,
        parent: QWidget | None = None,
        settings: QSettings | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("paramsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme, self.settings = theme, settings
        self.session: PlotSession[Dataset, CommonParams] | None = None
        self._bodies: dict[str, ParamsBody] = {}  # by plot key
        self._scrolls: dict[str, QScrollArea] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = PanelHeader(theme, "Ajuste do gráfico", "tune")
        self.back_button = header.add_button(IconButton(theme, "account_tree", "Voltar à árvore"))
        self.back_button.clicked.connect(self.back_requested)
        layout.addWidget(header)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self._placeholder_page = self._placeholder()
        self.stack.addWidget(self._placeholder_page)

    @property
    def body(self) -> QWidget:
        """The widget on screen: the current plot's body, or the "generate a plot" hint."""
        body = self._bodies.get(self.session.key) if self.session is not None else None
        return body if body is not None else self._placeholder_page

    # -- binding --------------------------------------------------------------------------------
    def bind(self, session: PlotSession[Dataset, CommonParams] | None) -> None:
        """Show the body of ``session`` (built if new or if its schema changed) with fresh values."""
        self.session = session
        if session is None:
            self.stack.setCurrentWidget(self._placeholder_page)
            return
        key = session.key
        body = self._bodies.get(key)
        if body is not None and (
            body.session is not session
            or body.schema != session.module.param_schema(session.dataset)
        ):
            self.discard(key)
            self.session = session
            body = None
        if body is None:
            body = self._build(session)
        self.stack.setCurrentWidget(self._scrolls[session.key])
        body.refresh_values()

    def discard(self, key: str) -> None:
        """Drop the body of the plot ``key`` (its tab closed or it is being regenerated)."""
        body = self._bodies.pop(key, None)
        scroll = self._scrolls.pop(key, None)
        if body is None or scroll is None:
            return
        if self.session is not None and self.session.key == key:
            self.session = None
            self.stack.setCurrentWidget(self._placeholder_page)
        self.stack.removeWidget(scroll)
        scroll.deleteLater()

    def refresh_values(self) -> None:
        """Push current parameter values into the widgets (after pan/zoom, reference change)."""
        body = self._current()
        if body is not None:
            body.refresh_values()

    def set_param(self, name: str, value: Any) -> None:
        """Edit a parameter of the current plot as if the user had changed its widget."""
        body = self._current()
        if body is not None:
            body.set_param(name, value)

    def update_readout(self) -> None:
        body = self._current()
        if body is not None:
            body.update_readout()

    # -- construction ---------------------------------------------------------------------------
    def _current(self) -> ParamsBody | None:
        return self._bodies.get(self.session.key) if self.session is not None else None

    def _build(self, session: PlotSession[Dataset, CommonParams]) -> ParamsBody:
        body = ParamsBody(self.theme, session, self.settings)
        body.changed.connect(self.changed)
        body.export_requested.connect(self.export_requested)
        body.remap_requested.connect(self.remap_requested)
        body.restore_requested.connect(self.restore_requested)
        scroll = QScrollArea()
        scroll.setObjectName("paramsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        self._bodies[session.key] = body
        self._scrolls[session.key] = scroll
        return body

    def _placeholder(self) -> QWidget:
        page = QWidget()
        page.setObjectName("paramsBody")
        layout = QVBoxLayout(page)
        hint = set_variant(
            QLabel("Gere um gráfico para ajustar\nos parâmetros de plotagem."), "fieldLabel"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = set_variant(QPushButton("Gerar gráfico"), "primary")
        button.setToolTip("Detectar o tipo de cálculo e plotar a pasta selecionada (Ctrl+G)")
        button.clicked.connect(self.generate_requested)
        layout.addStretch(1)
        layout.addWidget(hint)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return page
