"""Activity bar, top bar and status bar (PRD §2.1, mockups)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..theme.manager import ThemeManager
from .breadcrumb import Breadcrumb
from .common import IconButton, set_variant
from .spinner import CircularProgress

LED_TOKENS = {
    "online": "success",
    "offline": "error",
    "syncing": "warning",
    "unknown": "text_dim",
    "disabled": "text_dim",
}
LED_TIPS = {
    "online": "Cluster acessível",
    "offline": "Cluster inacessível",
    "syncing": "Sincronizando…",
    "unknown": "Verificando conexão…",
    "disabled": "Cluster não configurado (config.yaml)",
}


class StatusLed(QWidget):
    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.state = "unknown"
        self.setFixedSize(10, 10)
        theme.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str) -> None:
        self.update()

    def set_state(self, state: str) -> None:
        self.state = state
        self.setToolTip(LED_TIPS.get(state, state))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.theme.color(LED_TOKENS.get(self.state, "text_dim")))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()


class ActivityButton(IconButton):
    """Icon over a 9 px label; optional status dot (Rsync)."""

    def __init__(self, theme: ThemeManager, icon: str, text: str, tooltip: str, checkable=False):
        super().__init__(theme, icon, tooltip, "activity", "text_muted", "accent", 20)
        self.setText(text)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setCheckable(checkable)
        self.setFixedSize(QSize(46, 44))
        self.dot_state: str | None = None

    def set_dot(self, state: str | None) -> None:
        self.dot_state = state
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.dot_state is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.theme.color("chrome"), 1.5))
        painter.setBrush(self.theme.color(LED_TOKENS.get(self.dot_state, "text_dim")))
        painter.drawEllipse(self.width() - 15, 5, 7, 7)
        painter.end()


class ActivityBar(QWidget):
    explorer_requested = pyqtSignal()
    grid_toggled = pyqtSignal(bool)
    plot_requested = pyqtSignal()
    sync_requested = pyqtSignal()
    theme_requested = pyqtSignal()

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("activityBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(56)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 6, 5, 8)
        layout.setSpacing(4)
        self.tree = ActivityButton(theme, "account_tree", "Árvore", "Explorador de pastas", True)
        self.grid = ActivityButton(theme, "grid_view", "Grade", "Mostrar/ocultar arquivos", True)
        self.plot = ActivityButton(
            theme, "bolt", "Plot", "Mostrar/ocultar o gráfico (sem salvar)", True
        )
        self.rsync = ActivityButton(theme, "sync", "Rsync", "Sincronizar com o cluster")
        self.theme_button = ActivityButton(theme, "light_mode", "Tema", "Alternar tema (Ctrl+T)")
        for button in (self.tree, self.grid, self.plot, self.rsync):
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.tree.setChecked(True)
        self.grid.setChecked(True)

        self.tree.clicked.connect(self.explorer_requested)
        self.grid.toggled.connect(self.grid_toggled)
        self.plot.clicked.connect(self.plot_requested)
        self.rsync.clicked.connect(self.sync_requested)
        self.theme_button.clicked.connect(self.theme_requested)
        theme.theme_changed.connect(self._sync_theme_icon)
        self._sync_theme_icon()

    def set_left_mode(self, mode: str) -> None:
        self.tree.setChecked(mode == "tree")
        self.plot.setChecked(mode == "params")

    def set_cluster(self, _label: str, state: str) -> None:
        """The reachability dot of "Rsync" (none when the cluster is not configured)."""
        self.rsync.set_dot(None if state == "disabled" else state)

    def _sync_theme_icon(self, *_args) -> None:
        self.theme_button.set_icon_name("light_mode" if self.theme.name == "dark" else "dark_mode")


class TopBar(QWidget):
    generate_requested = pyqtSignal()
    plot_file_requested = pyqtSignal()
    panel_toggled = pyqtSignal(str, bool)  # "tree" | "grid" | "workspace"

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("topBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # History buttons and the clickable path (spec 16 R1, R2); disabled until there is somewhere
        # to go back or forward to.
        self.back_button = IconButton(theme, "arrow_back", "Voltar (Alt+←)")
        self.forward_button = IconButton(theme, "arrow_forward", "Avançar (Alt+→)")
        for button in (self.back_button, self.forward_button):
            button.setEnabled(False)
        self.breadcrumb = Breadcrumb()
        self.led = StatusLed(theme)
        self.cluster_label = QLabel()
        self.cluster_label.setObjectName("clusterLabel")
        separator = QWidget()
        separator.setObjectName("topSeparator")
        separator.setFixedHeight(18)
        separator.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout.addWidget(self.back_button)
        layout.addWidget(self.forward_button)
        layout.addWidget(self.breadcrumb)
        layout.addWidget(self.led)
        layout.addWidget(self.cluster_label)
        layout.addWidget(separator)
        self.toggles: dict[str, QToolButton] = {}
        for key, icon, text in (
            ("tree", "account_tree", "Árvore"),
            ("grid", "grid_view", "Grade"),
            ("workspace", "bubble_chart", "Gráficos"),
        ):
            button = IconButton(theme, icon, f"Mostrar/ocultar {text.lower()}", "toggle", size=14)
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setCheckable(True)
            button.setChecked(True)
            button.toggled.connect(lambda checked, k=key: self.panel_toggled.emit(k, checked))
            self.toggles[key] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.generate = set_variant(QPushButton("Gerar Gráfico"), "primary")
        self.generate.setObjectName("generateButton")
        self.generate.setToolTip("Detectar o tipo de cálculo e plotar a pasta selecionada (Ctrl+G)")
        self.generate.clicked.connect(self.generate_requested)
        layout.addWidget(self.generate)
        # Only while an output one module can plot on its own is open (the window decides).
        self.plot_file = QPushButton("Plotar SCF")
        self.plot_file.setObjectName("plotFileButton")
        self.plot_file.setToolTip("Plotar a convergência do SCF do arquivo aberto")
        self.plot_file.clicked.connect(self.plot_file_requested)
        self.plot_file.hide()
        layout.addWidget(self.plot_file)
        theme.theme_changed.connect(self._refresh_icons)
        self._refresh_icons()

    def set_root(self, root: Path) -> None:
        """The project the breadcrumb starts from."""
        self.breadcrumb.set_root(root)

    def set_path(self, folder: Path) -> None:
        self.breadcrumb.set_path(folder)

    def set_history(self, can_back: bool, can_forward: bool) -> None:
        self.back_button.setEnabled(can_back)
        self.forward_button.setEnabled(can_forward)

    def set_cluster(self, label: str, state: str) -> None:
        self.cluster_label.setText(label)
        self.led.set_state(state)

    def _refresh_icons(self, *_args) -> None:
        self.generate.setIcon(self.theme.icon("bolt", "primary_fg", size=14))
        self.plot_file.setIcon(self.theme.icon("monitoring", "text_secondary", size=14))


class StatusBar(QStatusBar):
    def __init__(self, theme: ThemeManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setSizeGripEnabled(False)
        # Detecting, loading or exporting a plot: a small spinner and what is going on (spec 15
        # R2). Replaces the global busy cursor; the message on its right is the usual one.
        self.spinner = CircularProgress(theme, 12)
        self.spinner.hide()
        self.busy = QLabel()
        self.busy.setObjectName("busyLabel")
        self.busy.hide()
        self.message = QLabel()
        self.readout = QLabel()
        self.path = QLabel()
        self.addWidget(self.spinner)
        self.addWidget(self.busy)
        self.addWidget(self.message, 1)
        self.addPermanentWidget(self.readout)
        self.addPermanentWidget(self.path)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        # Bound methods, not lambdas: a lambda slot outliving the widget's wrapper crashes.
        self._timer.timeout.connect(self._clear_message)

    def set_message(self, text: str, level: str = "info", timeout_ms: int = 0) -> None:
        self.message.setText(text)
        self.message.setProperty("level", level)
        style = self.message.style()
        if style is not None:
            style.unpolish(self.message)
            style.polish(self.message)
        if timeout_ms:
            self._timer.start(timeout_ms)
        else:
            self._timer.stop()

    def _clear_message(self) -> None:
        self.set_message("")

    def set_busy(self, text: str | None) -> None:
        """Show the spinner with ``text``; None hides both."""
        self.busy.setText(text or "")
        self.spinner.setVisible(text is not None)
        self.busy.setVisible(text is not None)

    def set_readout(self, text: str) -> None:
        self.readout.setText(text)

    def set_path(self, text: str) -> None:
        self.path.setText(text)
