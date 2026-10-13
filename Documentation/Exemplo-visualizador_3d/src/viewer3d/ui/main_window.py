"""Main window: menus, splitter (left panel | canvas) and status bar."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QWidget,
)

from viewer3d.core.example import SI_DIAMOND_INPUT
from viewer3d.core.qe_input import parse_input, read_structure
from viewer3d.core.structure import AtomRef, Structure, StructureError
from viewer3d.ui.canvas import Canvas
from viewer3d.ui.options import STYLES
from viewer3d.ui.panels import LeftPanel, atom_title

PANEL_WIDTH = 320
FILE_FILTER = "Inputs do Quantum ESPRESSO (*.in *.pwi *.inp);;Todos os arquivos (*)"


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("viewer3d")
        self.setAcceptDrops(True)
        self.last_error: str | None = None
        self._last_dir = os.getcwd()

        self.canvas = Canvas()
        self.panel = LeftPanel(self.canvas)
        self.panel.setMinimumWidth(280)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.panel)
        self.splitter.addWidget(self.canvas)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([PANEL_WIDTH, 900])
        self.setCentralWidget(self.splitter)

        self._build_status_bar()
        self._build_menus()
        self.panel.neighbor_clicked.connect(self._neighbor_clicked)
        self.canvas.hovered.connect(self._show_hover)
        self.canvas.frame_rendered.connect(self._show_frame_time)
        self.canvas.options_changed.connect(self._sync_view_menu)
        self.resize(1280, 820)

    # --- construction -------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self._info = QLabel("Nenhum arquivo aberto")
        self._hover = QLabel("")
        self._warning = QLabel("")
        self._frame = QLabel("")
        self._hover.setMinimumWidth(110)
        self._frame.setMinimumWidth(90)
        self._frame.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar.addWidget(self._info, 1)
        bar.addPermanentWidget(self._hover)
        bar.addPermanentWidget(self._warning)
        bar.addPermanentWidget(self._frame)

    def _action(self, menu, text: str, slot, shortcut: str | None = None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Arquivo")
        self._action(file_menu, "&Abrir…", self.open_dialog, "Ctrl+O")
        self._action(file_menu, "Abrir exemplo (&Si)", self.open_example)
        file_menu.addSeparator()
        self._action(file_menu, "&Sair", self.close, "Ctrl+Q")

        view = self.menuBar().addMenu("&Exibir")
        style_menu = view.addMenu("Estilo")
        self._style_actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        for key, text in STYLES.items():
            action = self._action(
                style_menu, text, lambda _=False, k=key: self.set_style(k), checkable=True
            )
            group.addAction(action)
            self._style_actions[key] = action
        self._style_actions[self.canvas.options.style].setChecked(True)
        self._persp = self._action(
            view, "Projeção em &perspectiva", self._toggle_perspective, checkable=True
        )
        self._persp.setChecked(self.canvas.options.perspective)
        view.addSeparator()
        along = view.addMenu("Vista ao longo de")
        for name in "abcxyz":
            self._action(along, name, lambda _=False, n=name: self.canvas.view_along(n))
        self._action(view, "&Resetar vista", self.canvas.reset_view)

    # --- opening ------------------------------------------------------------------------
    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir input do pw.x", self._last_dir, FILE_FILTER
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str | os.PathLike[str]) -> bool:
        result = read_structure(path)
        if isinstance(result, StructureError):
            self._report_error(result.message)
            return False
        self._last_dir = str(Path(path).resolve().parent)
        self.show_structure(result)
        return True

    def open_example(self) -> None:
        result = parse_input(SI_DIAMOND_INPUT)
        if isinstance(result, Structure):
            self.show_structure(result, name="Si (exemplo)")

    def show_structure(self, structure: Structure, name: str | None = None) -> None:
        self.last_error = None
        self.canvas.set_structure(structure)
        self.panel.structure_changed()
        source = structure.source
        shown = name or (Path(source.path).name if source.path else "sem nome")
        self.setWindowTitle(f"viewer3d — {shown}")
        parts = (shown, structure.formula, f"nat = {source.nat}", f"ibrav = {source.ibrav}")
        self._info.setText("   ·   ".join(parts))
        if source.warnings:
            self._warning.setText("⚠")
            self._warning.setToolTip("\n".join(source.warnings))
        else:
            self._warning.setText("")
            self._warning.setToolTip("")
        self.statusBar().clearMessage()

    def _report_error(self, message: str) -> None:
        self.last_error = message
        self.statusBar().showMessage(f"Erro: {message}", 15000)
        QMessageBox.warning(self, "Não foi possível abrir o arquivo", message)

    # --- drag and drop ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
                break

    # --- view menu and status -----------------------------------------------------------
    def set_style(self, key: str) -> None:
        self.canvas.options.style = key
        self.canvas.refresh_options()
        self.panel.display.sync()
        self._style_actions[key].setChecked(True)

    def _toggle_perspective(self) -> None:
        self.canvas.options.perspective = self._persp.isChecked()
        self.canvas.refresh_options()
        self.panel.display.sync()

    def _sync_view_menu(self) -> None:
        self._persp.setChecked(self.canvas.options.perspective)
        self._style_actions[self.canvas.options.style].setChecked(True)

    def _neighbor_clicked(self, ref: AtomRef) -> None:
        self.canvas.select(ref)

    def _show_hover(self, ref: AtomRef | None) -> None:
        structure = self.canvas.structure
        self._hover.setText("" if ref is None or structure is None else atom_title(structure, ref))

    def _show_frame_time(self, ms: float) -> None:
        self._frame.setText(f"{ms:.1f} ms")
