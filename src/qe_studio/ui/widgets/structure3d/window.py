"""One "Visualização 3D" window (spec 43 R4.3): a top-level window without a parent (its own taskbar
entry, it may stay behind the main one), one per click, each with its own options, camera and current
atom. It opens with the ``options`` and ``camera`` it is given (spec 47: the controller reads them from
``view3d.plot``), else with the defaults and the background of the app theme at that moment, and
``view_session()`` gives its view back. The window itself never writes ``view3d.plot`` (the controller
does, when it closes: a window opened without it, as the tests' helper does on fixtures, saves nothing);
the one file it writes is the picture of its "Print" (spec 46 R5), under ``plots/``.

The window emits ``closed(self)`` from its ``closeEvent``, so whoever keeps it drops it there (never
through ``destroyed``).

"Visualizar 3D" of "Criar cálculo" (spec 81) shows structures that may not be files yet: ``show_structure``
swaps the one shown (the window is not made again), ``set_choices`` puts the "Estrutura" combo after
"Print" (``choice_changed`` says what the user picked), and a structure without a path has its "Print"
off and its file's ``name`` in the title.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QComboBox,
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
from ....core.structure3d.image_file import print_stem
from ....core.structure3d.model import AtomRef, Structure, atom_name
from ....core.structure3d.options import DisplayOptions, background_of_theme
from ....core.structure3d.view_state import CameraState, session_of
from ....core.tasks import run_task
from ....i18n import _
from ...theme.manager import ThemeManager
from ..common import IconButton, set_variant
from .canvas import StructureCanvas
from .panel import StructurePanel
from .print_image import save_view

log = logging.getLogger(__name__)

TITLE = _("Visualização 3D")
PANEL_WIDTH = 320
SIZE = (1280, 820)
VIEWS = ("x", "y", "z")  # the menu of the bar; the keys A, B, C still look along a, b, c
VIEW_TIP = _("Olhar ao longo de x, y ou z (as teclas A, B e C olham ao longo de a, b e c)")
MESSAGE_MS = 3000  # a status bar notice ("Medidas copiadas")
FAILED_MS = 8000  # the notice of a "Print" that failed
PRINT_TEXT = _("Print")
PRINT_TIP = _("Salvar a imagem da vista em PNG, na pasta plots/ do cálculo")
UNSAVED_TIP = _("A estrutura ainda não foi gravada: crie o cálculo para salvar a imagem")
FIXED_TEXT = _("Átomos fixos")
FIXED_TIP = _("Destacar os átomos com if_pos 0 no input ({n} de {m})")
NOT_FIXED_TIP = _("Este input não fixa nenhum átomo (if_pos)")
CHOICE_NAME = _("Estrutura")
CHOICE_TIP = _("Estrutura mostrada: a do SCF ou a de um input gerado")
PRINT_SCALE = 2  # the picture has this many times the pixels of the view


def window_title(structure: Structure, name: str | None = None) -> str:
    """``scf.in — Analise_1 · Visualização 3D``; ``name``: the file of a structure without a path."""
    path = Path(structure.source.path or name or "input")
    return (
        f"{path.name} — {path.parent.name} · {TITLE}"
        if path.parent.name
        else f"{path.name} · {TITLE}"
    )


def status_text(structure: Structure, name: str | None = None) -> str:
    """``scf.in · CH18Al8HgO36Si8 · nat = 72 · ibrav = 0``."""
    source = structure.source
    shown = Path(source.path).name if source.path else name or "input"
    return f"{shown} · {structure.formula} · nat = {source.nat} · ibrav = {source.ibrav}"


def _reason(exc: BaseException) -> str:
    """Why a "Print" failed, in words for the status bar."""
    if isinstance(exc, FileNotFoundError):
        return _("a pasta do cálculo não existe mais")
    if isinstance(exc, OSError) and exc.strerror:
        return exc.strerror
    return str(exc) or type(exc).__name__


class StructureWindow(QMainWindow):
    closed = pyqtSignal(object)  # this window, from closeEvent
    image_saved = pyqtSignal(object)  # the Path of the PNG a "Print" wrote
    print_failed = pyqtSignal(str)  # the reason
    choice_changed = pyqtSignal(int)  # the index the user picked in the "Estrutura" combo (spec 81)

    def __init__(
        self,
        structure: Structure,
        theme: ThemeManager,
        settings: QSettings | None = None,
        *,
        options: DisplayOptions | None = None,
        camera: CameraState | None = None,
        root: Callable[[], Path | None] | None = None,
        name: str | None = None,
    ):
        """``name``: the file's name, for a structure that has no path yet (spec 81)."""
        super().__init__(None)  # top level on purpose: independent of the main window
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("structureWindow")
        self.structure, self.name = structure, name
        self._root = root  # the project root, asked at every "Print" (names the file, spec 32)
        if options is None:
            options = DisplayOptions(background=background_of_theme(theme.name))
        self.canvas = StructureCanvas(theme, structure, options)
        if camera is not None:
            self.canvas.restore_camera(camera)  # before the first frame, which then keeps it
        self.panel = StructurePanel(theme, self.canvas, settings)  # shows the options as given

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
        self.canvas.options_changed.connect(self._fixed_state)
        self.panel.measures.message.connect(self._show_message)
        self.setWindowTitle(window_title(structure, name))
        self._print_state()
        self._fixed_state()
        self.resize(*SIZE)
        self.canvas.setFocus()

    # -- another structure (spec 81) ---------------------------------------------------------------
    def show_structure(
        self, structure: Structure, keep_camera: bool = False, name: str | None = None
    ) -> None:
        """Show ``structure`` in this window: the display options stay, and the camera too with
        ``keep_camera`` (the same cell); the title, the status bar, "Print" and "Átomos fixos" are the
        new one's."""
        self.structure, self.name = structure, name
        self.canvas.set_structure(structure, keep_camera)
        self.panel.set_structure(structure)
        self.setWindowTitle(window_title(structure, name))
        self.info.setText(status_text(structure, name))
        self._show_warnings()
        self._print_state()
        self._fixed_state()

    def set_choices(self, labels: list[str], current: int) -> None:
        """The structures to pick from, ``current`` the one shown; the combo shows with two or more."""
        combo = self.choice_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(labels)
        combo.setCurrentIndex(current)
        combo.blockSignals(False)
        combo.setVisible(len(labels) > 1)

    def show_notice(self, text: str) -> None:
        """A sentence in the status bar for a while (a structure that could not be made, spec 81)."""
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage(text, FAILED_MS)

    def _print_state(self) -> None:
        """ "Print" needs a file to put plots/ next to: off, with the reason, for one not written yet."""
        saved = bool(self.structure.source.path)
        self.print_button.setEnabled(saved)
        self.print_button.setToolTip(PRINT_TIP if saved else UNSAVED_TIP)

    def _fixed_state(self) -> None:
        """ "Átomos fixos" follows the option, and is off, with the reason, for an input that fixes no
        atom; the option stays, so another structure with fixed atoms shows them again (spec 88)."""
        total = len(self.structure)
        count = int(self.structure.fixed.sum())
        button = self.fixed_button
        button.setEnabled(count > 0)
        button.setChecked(count > 0 and self.canvas.options.show_fixed)
        button.setToolTip(FIXED_TIP.format(n=count, m=total) if count else NOT_FIXED_TIP)

    def _fixed_clicked(self, checked: bool) -> None:
        self.canvas.options.show_fixed = checked
        self.canvas.refresh_options()

    def _bar(self, theme: ThemeManager) -> QWidget:
        """Above the view, like a plot's: "Resetar vista", the "Vista" menu, "Átomos fixos", "Print" and
        the "Estrutura" combo (hidden until there are two structures to pick from, spec 81)."""
        bar = QWidget()
        bar.setObjectName("plotToolbar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        self.reset_button = IconButton(
            theme, "home", _("Resetar vista (R)"), "plotTool", "text_secondary", "accent", 15
        )
        self.reset_button.setText(_("Resetar vista"))
        self.reset_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.reset_button.clicked.connect(self._reset_clicked)
        self.view_button = set_variant(QToolButton(), "plotTool")
        self.view_button.setText(_("Vista"))
        self.view_button.setToolTip(VIEW_TIP)
        self.view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.view_button)
        self.view_actions: dict[str, QAction] = {}
        for name in VIEWS:
            action = menu.addAction(
                _("Ao longo de {axis} ({key})").format(axis=name, key=name.upper())
            )
            assert action is not None
            action.triggered.connect(lambda _=False, n=name: self.canvas.view_along(n))
            self.view_actions[name] = action
        self.view_button.setMenu(menu)
        self.fixed_button = set_variant(QToolButton(), "plotTool")
        self.fixed_button.setText(FIXED_TEXT)
        self.fixed_button.setCheckable(True)
        self.fixed_button.clicked.connect(self._fixed_clicked)
        self.print_button = IconButton(
            theme, "image", PRINT_TIP, "plotTool", "text_secondary", "accent", 15
        )
        self.print_button.setText(PRINT_TEXT)
        self.print_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.print_button.clicked.connect(self._print_clicked)
        self.choice_combo = QComboBox()
        self.choice_combo.setAccessibleName(CHOICE_NAME)
        self.choice_combo.setToolTip(CHOICE_TIP)
        self.choice_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.choice_combo.activated.connect(self.choice_changed)
        self.choice_combo.hide()
        layout.addWidget(self.reset_button)
        layout.addWidget(self.view_button)
        layout.addWidget(self.fixed_button)
        layout.addWidget(self.print_button)
        layout.addWidget(self.choice_combo)
        layout.addStretch(1)
        return bar

    def _reset_clicked(self) -> None:
        self.canvas.reset_view()

    def view_session(self) -> dict:
        """The section of ``view3d.plot`` for this view (spec 47): the options and, once the view has
        been framed, the camera."""
        canvas = self.canvas
        camera = CameraState.of(canvas.camera) if canvas.framed else None
        return session_of(self.structure, canvas.options, camera)

    # -- Print (spec 46 R5) ------------------------------------------------------------------------
    def _print_clicked(self) -> None:
        """The view as it is (camera, options, background, current atom and measure badges: not the
        focus or hover ring) at ``PRINT_SCALE`` times its size, saved to ``plots/`` by a task."""
        source = self.structure.source.path
        if not source:
            return
        path = Path(source)
        root = self._root() if self._root is not None else None
        stem = print_stem(path, root)
        image = self.canvas.render_image(self.canvas.size(), draft=False, dpr=PRINT_SCALE)
        run_task(
            save_view,
            image,
            path.parent,
            stem,
            on_done=self._print_done,
            on_error=self._print_error,
        )

    def _print_done(self, target: Path) -> None:
        log.info("file: 3D image %s", target)
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage(_("Imagem salva em plots/{name}").format(name=target.name), MESSAGE_MS)
        self.image_saved.emit(target)

    def _print_error(self, exc: BaseException) -> None:
        reason = _reason(exc)
        bar = self.statusBar()
        if bar is not None:
            text = _("Não foi possível salvar a imagem: {reason}").format(reason=reason)
            bar.showMessage(text, FAILED_MS)
        self.print_failed.emit(reason)

    def _status(self) -> None:
        bar = self.statusBar()
        assert bar is not None
        bar.setObjectName("structureStatus")
        self.info = set_variant(QLabel(status_text(self.structure, self.name)), "readout")
        self.hover = set_variant(QLabel(""), "readout")
        self.warning = set_variant(QLabel("⚠"), "warning")
        self._show_warnings()
        bar.addWidget(self.info, 1)
        bar.addPermanentWidget(self.hover)
        bar.addPermanentWidget(self.warning)

    def _show_warnings(self) -> None:
        warnings = self.structure.source.warnings
        self.warning.setToolTip("\n".join(warnings))
        self.warning.setVisible(bool(warnings))

    def _show_hover(self, ref: AtomRef | None) -> None:
        if ref is None:
            self.hover.setText("")
            return
        element = element_for_label(self.structure.labels[ref.index])
        self.hover.setText(f"{atom_name(self.structure, ref)} · {element.name}")

    def _show_message(self, text: str) -> None:
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage(text, MESSAGE_MS)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802 (Qt naming)
        self.closed.emit(self)
        super().closeEvent(event)
