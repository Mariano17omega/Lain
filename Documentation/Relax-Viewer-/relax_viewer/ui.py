from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .diagnostics import NOT_RELAXED, RELAXED, status_label, status_summary
from .parser import parse_relax_output

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

MAIN_STYLE = """
QMainWindow {
    background-color: #0f172a;
}

#CentralWidget {
    background-color: #0f172a;
    font-family: 'Segoe UI', 'Inter', 'Outfit', Arial, sans-serif;
}

#CentralWidget QLabel {
    color: #f8fafc;
}

#CentralWidget QPushButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}

#CentralWidget QPushButton:hover {
    background-color: #2563eb;
}

#CentralWidget QPushButton:pressed {
    background-color: #1d4ed8;
}

#CentralWidget QTabWidget::pane {
    border: 1px solid #334155;
    background: #1e293b;
    border-radius: 8px;
}

#CentralWidget QTabBar::tab {
    background: #0f172a;
    border: 1px solid #334155;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    color: #94a3b8;
    margin-right: 4px;
}

#CentralWidget QTabBar::tab:hover {
    background: #1e293b;
    color: #f8fafc;
}

#CentralWidget QTabBar::tab:selected {
    background: #1e293b;
    border-color: #334155;
    color: #3b82f6;
}
"""


class KPICard(QWidget):
    def __init__(self, title: str, val: str = "-") -> None:
        super().__init__()
        self.setObjectName("KPICard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;")
        
        self.value_lbl = QLabel(val)
        self.value_lbl.setStyleSheet("color: #f8fafc; font-size: 16px; font-weight: 700;")
        
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)
        
        self.setStyleSheet("""
            QWidget#KPICard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)

    def set_value(self, val: str) -> None:
        self.value_lbl.setText(val)


class PlotPane(QWidget):
    """Tab pane containing a matplotlib canvas plus type-specific controls."""

    _ZOOM_STEP = 1.35
    _ZOOM_MIN  = 0.10
    _ZOOM_MAX  = 15.0
    _ROT_STEP  = 15.0   # degrees per click

    # Small square button style used in the left control panel
    _CTRL_BTN = """
        QPushButton {
            background-color: #334155 !important;
            color: #ffffff !important;
            border: 1px solid #475569 !important;
            border-radius: 4px !important;
            font-size: 13px !important;
            font-weight: bold !important;
            padding: 0px !important;
            margin: 0px !important;
        }
        QPushButton:hover  { background-color: #475569 !important; color: #ffffff !important; border-color: #64748b !important; }
        QPushButton:pressed{ background-color: #3b82f6 !important; color: #ffffff !important; }
    """

    # Flat toggle button for energy/force toolbar
    _TOGGLE_BTN = """
        QPushButton {
            background-color: #334155;
            color: #ffffff;
            border: 1px solid #475569;
            border-radius: 5px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton:hover  { background-color: #475569; color: #ffffff; border-color: #64748b; }
        QPushButton:pressed{ background-color: #3b82f6; color: #ffffff; }
    """

    def __init__(self, plot_type: str) -> None:
        super().__init__()
        self._plot_type = plot_type
        self._log_scale: bool = True
        self._zoom: float = 1.0
        self._elev: float = 30.0
        self._azim: float = -60.0
        self._result = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        self._fig = Figure(dpi=100)
        self._fig.patch.set_facecolor("#1e293b")
        self._canvas = FigureCanvas(self._fig)

        if plot_type == "structure":
            self._ax = self._fig.add_subplot(111, projection="3d")
            self._ax.set_facecolor("#1e293b")

            # ── Left control panel (Rotation row + Zoom column) ────────
            ctrl_left = QWidget()
            ctrl_left.setFixedWidth(112)
            ctrl_left.setStyleSheet("background: transparent;")
            cl = QVBoxLayout(ctrl_left)
            cl.setContentsMargins(4, 4, 4, 4)
            cl.setSpacing(4)

            def _sec(text: str) -> QLabel:
                lbl = QLabel(text)
                lbl.setStyleSheet(
                    "color:#94a3b8;font-size:10px;font-weight:700;"
                    "text-transform:uppercase;letter-spacing:0.5px;"
                )
                return lbl

            def _cbtn(symbol: str, w: int = 24, h: int = 24) -> QPushButton:
                b = QPushButton(symbol)
                b.setFixedSize(w, h)
                b.setStyleSheet(self._CTRL_BTN)
                return b

            # ── Rotation row ───────────────────────────────────────────
            cl.addWidget(_sec("Girar"))

            self._rot_up    = _cbtn("▲", 24, 24)
            self._rot_down  = _cbtn("▼", 24, 24)
            self._rot_left  = _cbtn("◀", 24, 24)
            self._rot_right = _cbtn("▶", 24, 24)

            self._rot_up.clicked.connect(
                lambda: self._rotate(delev=+self._ROT_STEP))
            self._rot_down.clicked.connect(
                lambda: self._rotate(delev=-self._ROT_STEP))
            self._rot_left.clicked.connect(
                lambda: self._rotate(dazim=-self._ROT_STEP))
            self._rot_right.clicked.connect(
                lambda: self._rotate(dazim=+self._ROT_STEP))

            rot_row = QHBoxLayout()
            rot_row.setContentsMargins(0, 0, 0, 0)
            rot_row.setSpacing(2)
            rot_row.addWidget(self._rot_up)
            rot_row.addWidget(self._rot_down)
            rot_row.addWidget(self._rot_left)
            rot_row.addWidget(self._rot_right)
            cl.addLayout(rot_row)
            cl.addSpacing(10)

            # ── Zoom vertical column ──────────────────────────────────
            cl.addWidget(_sec("Zoom"))

            self._zoom_in_btn    = _cbtn("+", 32, 24)
            self._zoom_out_btn   = _cbtn("-", 32, 24)
            self._zoom_reset_btn = _cbtn("⦻", 32, 24)

            self._zoom_in_btn.setToolTip("Aumentar zoom")
            self._zoom_out_btn.setToolTip("Diminuir zoom")
            self._zoom_reset_btn.setToolTip("Resetar zoom e ângulo")

            self._zoom_in_btn.clicked.connect(self._zoom_in)
            self._zoom_out_btn.clicked.connect(self._zoom_out)
            self._zoom_reset_btn.clicked.connect(self._zoom_reset)

            zoom_col = QVBoxLayout()
            zoom_col.setContentsMargins(0, 0, 0, 0)
            zoom_col.setSpacing(4)
            zoom_col.addWidget(self._zoom_in_btn)
            zoom_col.addWidget(self._zoom_out_btn)
            zoom_col.addWidget(self._zoom_reset_btn)
            cl.addLayout(zoom_col)

            cl.addStretch(1)

            # ── Right legend panel ─────────────────────────────────────
            ctrl_right = QWidget()
            ctrl_right.setFixedWidth(88)
            ctrl_right.setStyleSheet("background: transparent;")
            cr = QVBoxLayout(ctrl_right)
            cr.setContentsMargins(4, 4, 4, 4)
            cr.setSpacing(4)

            cr.addWidget(_sec("Elem."))
            self._legend_vbox = QVBoxLayout()
            self._legend_vbox.setSpacing(1)
            self._legend_vbox.setContentsMargins(0, 0, 0, 0)
            cr.addLayout(self._legend_vbox)
            cr.addStretch(1)

            # ── Assemble content row (Left Ctrl -> Canvas -> Right Legend) ──
            content = QHBoxLayout()
            content.setContentsMargins(0, 0, 0, 0)
            content.setSpacing(4)
            content.addWidget(ctrl_left)
            content.addWidget(self._canvas, stretch=1)
            content.addWidget(ctrl_right)
            outer.addLayout(content, stretch=1)

        else:  # energy / force
            self._ax = self._fig.add_subplot(111)
            self._ax.set_facecolor("#1e293b")

            # Scale toggle toolbar (top-right)
            toolbar = QHBoxLayout()
            toolbar.setContentsMargins(0, 0, 0, 2)
            toolbar.addStretch(1)
            self._scale_btn = QPushButton("Escala: Log")
            self._scale_btn.setFixedWidth(120)
            self._scale_btn.setStyleSheet(self._TOGGLE_BTN)
            self._scale_btn.clicked.connect(self._toggle_scale)
            toolbar.addWidget(self._scale_btn)
            outer.addLayout(toolbar)
            outer.addWidget(self._canvas, stretch=1)

        self.clear()

    # ── Legend helpers ─────────────────────────────────────────────────
    def _clear_legend_panel(self) -> None:
        if self._plot_type != "structure":
            return
        while self._legend_vbox.count():
            item = self._legend_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate_legend_panel(self, result) -> None:
        if self._plot_type != "structure":
            return
        from .plotting import CPK_COLORS
        self._clear_legend_panel()
        elements = sorted(set(a.element for a in result.structure.atoms))
        for el in elements:
            color = CPK_COLORS.get(el, "#d1d5db")
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 2, 0, 2)
            row_l.setSpacing(4)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color};font-size:14px;")
            dot.setFixedWidth(16)
            name = QLabel(el)
            name.setStyleSheet(
                "color:#e2e8f0;font-size:11px;font-weight:600;"
            )
            row_l.addWidget(dot)
            row_l.addWidget(name)
            row_l.addStretch(1)
            self._legend_vbox.addWidget(row_w)

    # ── Interaction handlers ───────────────────────────────────────────
    def _toggle_scale(self) -> None:
        self._log_scale = not self._log_scale
        self._scale_btn.setText(
            "Escala: Log" if self._log_scale else "Escala: Linear"
        )
        if self._result is not None:
            self.draw_result(self._result)

    def _zoom_in(self) -> None:
        self._zoom = min(self._zoom * self._ZOOM_STEP, self._ZOOM_MAX)
        if self._result is not None:
            self.draw_result(self._result)

    def _zoom_out(self) -> None:
        self._zoom = max(self._zoom / self._ZOOM_STEP, self._ZOOM_MIN)
        if self._result is not None:
            self.draw_result(self._result)

    def _zoom_reset(self) -> None:
        self._zoom = 1.0
        self._elev = 30.0
        self._azim = -60.0
        if self._result is not None:
            self.draw_result(self._result)

    def _rotate(self, delev: float = 0.0, dazim: float = 0.0) -> None:
        # Unlimited rotation in all directions — no clamping
        self._elev += delev
        self._azim = (self._azim + dazim) % 360.0
        if self._result is not None:
            self.draw_result(self._result)

    # ── Public API ─────────────────────────────────────────────────────
    def clear(self) -> None:
        self._result = None
        self._zoom = 1.0
        self._elev = 30.0
        self._azim = -60.0
        self._ax.clear()
        self._ax.set_facecolor("#1e293b")

        if self._plot_type == "structure":
            self._clear_legend_panel()
            from .plotting import _draw_empty_3d
            _draw_empty_3d(self._ax, "Nenhuma estrutura carregada.")
        else:
            from .plotting import _draw_empty
            _draw_empty(self._ax, "Nenhum gráfico carregado.")

        self._canvas.draw()

    def draw_result(self, result) -> None:
        self._result = result
        self._ax.clear()
        self._ax.set_facecolor("#1e293b")

        if self._plot_type == "energy":
            from .plotting import draw_energy_on_ax
            draw_energy_on_ax(self._ax, result, log_scale=self._log_scale)
            self._fig.tight_layout()

        elif self._plot_type == "force":
            from .plotting import draw_force_on_ax
            draw_force_on_ax(self._ax, result, log_scale=self._log_scale)
            self._fig.tight_layout()

        elif self._plot_type == "structure":
            from .plotting import draw_structure_on_ax
            draw_structure_on_ax(
                self._ax, result,
                zoom=self._zoom,
                elev=self._elev,
                azim=self._azim,
                show_legend=False,
            )
            self._populate_legend_panel(result)
            # Push axes to fill the canvas — tight_layout adds wasteful margins
            self._fig.subplots_adjust(
                left=-0.04, right=1.04, bottom=-0.08, top=1.0
            )

        self._canvas.draw()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Relax Viewer")
        self.resize(1024, 768)
        self.setStyleSheet(MAIN_STYLE)

        # Header Row
        logo_lbl = QLabel("RELAX VIEWER")
        logo_lbl.setStyleSheet("color: #3b82f6; font-size: 18px; font-weight: 800; letter-spacing: 1px;")
        
        self._select_button = QPushButton("Selecionar output")
        self._select_button.clicked.connect(self._select_output)

        self._file_name_label = QLabel("Nenhum arquivo selecionado")
        self._file_name_label.setStyleSheet("color: #94a3b8; font-size: 13px; font-style: italic;")

        top_layout = QHBoxLayout()
        top_layout.addWidget(logo_lbl)
        top_layout.addSpacing(20)
        top_layout.addWidget(self._file_name_label)
        top_layout.addStretch(1)
        top_layout.addWidget(self._select_button)

        # KPI Row
        self._status_card = KPICard("Status do Relaxamento", "Pendente")
        self._update_status_card("Pendente")
        
        self._steps_card = KPICard("Passos Completos", "-")
        self._energy_card = KPICard("Último |ΔE|", "-")
        self._force_card = KPICard("Última Força", "-")

        kpi_layout = QHBoxLayout()
        kpi_layout.addWidget(self._status_card)
        kpi_layout.addWidget(self._steps_card)
        kpi_layout.addWidget(self._energy_card)
        kpi_layout.addWidget(self._force_card)

        # Plot tabs
        self._energy_pane = PlotPane("energy")
        self._force_pane = PlotPane("force")
        self._structure_pane = PlotPane("structure")

        self._tabs = QTabWidget()
        self._tabs.addTab(self._energy_pane, "Energia")
        self._tabs.addTab(self._force_pane, "Força")
        self._tabs.addTab(self._structure_pane, "Estrutura")

        # Summary box
        self._summary_card = QWidget()
        self._summary_card.setObjectName("SummaryCard")
        summary_layout = QVBoxLayout(self._summary_card)
        summary_layout.setContentsMargins(14, 14, 14, 14)
        
        self._summary_title = QLabel("Sumário de Diagnósticos")
        self._summary_title.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 700; border-bottom: 1px solid #334155; padding-bottom: 6px; text-transform: uppercase;")
        
        self._summary_label = QLabel("Selecione um arquivo relax.out para avaliar o relaxamento.")
        self._summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.5;")
        
        summary_layout.addWidget(self._summary_title)
        summary_layout.addWidget(self._summary_label)
        
        self._summary_card.setStyleSheet("""
            QWidget#SummaryCard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)

        # Main Layout Assembly
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        layout.addLayout(top_layout)
        layout.addLayout(kpi_layout)
        layout.addWidget(self._tabs, stretch=1)
        layout.addWidget(self._summary_card)

        central = QWidget()
        central.setObjectName("CentralWidget")
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _update_status_card(self, status: str) -> None:
        self._status_card.set_value(status)
        if status == RELAXED:
            self._status_card.value_lbl.setStyleSheet("color: #10b981; font-size: 16px; font-weight: 700;")
        elif status == NOT_RELAXED:
            self._status_card.value_lbl.setStyleSheet("color: #ef4444; font-size: 16px; font-weight: 700;")
        else:
            self._status_card.value_lbl.setStyleSheet("color: #94a3b8; font-size: 16px; font-weight: 700;")

    def _select_output(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar output do Quantum ESPRESSO",
            str(Path.cwd()),
            "Outputs (*.out *.log *.txt);;Todos os arquivos (*)",
        )
        if filename:
            self.load_output(Path(filename))

    def load_output(self, path: Path) -> None:
        try:
            result = parse_relax_output(path)
        except Exception as exc:
            self._set_error(f"Erro ao processar {path}:\n{exc}")
            return

        status = status_label(result)
        self._update_status_card(status)
        self._steps_card.set_value(str(len(result.steps)))

        last_delta = result.energy_deltas[-1].delta_ry if result.energy_deltas else None
        if last_delta is not None:
            self._energy_card.set_value(f"{last_delta:.3e} Ry")
        else:
            self._energy_card.set_value("-")

        final_step = result.final_step
        if final_step is not None:
            self._force_card.set_value(f"{final_step.total_force_ry_bohr:.3e} Ry/Bohr")
        else:
            self._force_card.set_value("-")

        self._file_name_label.setText(path.name)
        self._file_name_label.setToolTip(str(path))
        self._summary_label.setText(status_summary(result))

        # Renderizar nos canvases interativos
        self._energy_pane.draw_result(result)
        self._force_pane.draw_result(result)
        self._structure_pane.draw_result(result)

    def _set_error(self, message: str) -> None:
        self._update_status_card(NOT_RELAXED)
        self._steps_card.set_value("Erro")
        self._energy_card.set_value("Erro")
        self._force_card.set_value("Erro")
        self._file_name_label.setText("Erro de processamento")
        self._summary_label.setText(message)
        self._energy_pane.clear()
        self._force_pane.clear()
        self._structure_pane.clear()

