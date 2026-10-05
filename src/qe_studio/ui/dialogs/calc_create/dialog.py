"""The "Criar cálculo" window (spec 26 R2): step 1 (configuração) and step 2 (arquivos) in one
non-modal dialog, like the sync window's pages.

Nothing is written here: "Criar" asks the controller (``create_requested``), which writes in a
worker and closes the window on success. Esc, the close button and "Cancelar" never create
anything; with fields edited or notes written they ask first. The "Padrão / Avançado" switch of
step 2 (spec 28) is remembered in QSettings ``calc_create/mode``.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ....core.calc_create.scf_info import ScfInfo
from ....core.calc_create.types import DEFAULT_MODE, MODES, CalcPlan, CalcType, Mode
from ....core.config import JobsConfig
from ...busy import BusyTracker
from ...theme.manager import ThemeManager
from ...widgets.common import set_variant
from .mode_switch import ModeSwitch
from .setup_page import SetupPage
from .tabs_page import DEBOUNCE_MS, TabsPage

TITLE = "Criar cálculo"
STEP_SETUP = "1 · Configuração"
STEP_FILES = "2 · Arquivos"
MODE_KEY = "calc_create/mode"


class CreateRequest(NamedTuple):
    parent: Path
    calc_type: CalcType
    suffix: str
    plan: CalcPlan
    notes: str


def ask_discard(parent: QWidget) -> bool:
    answer = QMessageBox.question(
        parent,
        TITLE,
        "Descartar o que foi preenchido?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


class CalcCreateDialog(QDialog):
    create_requested = pyqtSignal(object)  # CreateRequest

    def __init__(
        self,
        theme: ThemeManager,
        root: Path,
        start: Path,
        jobs: JobsConfig,
        busy: BusyTracker | None = None,
        parent: QWidget | None = None,
        settings: QSettings | None = None,
    ):
        """``settings``: where the mode is remembered (None: not remembered, ``padrao``)."""
        super().__init__(parent)
        self.setObjectName("calcCreateDialog")
        self.setWindowTitle(TITLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(960, 640)
        self.theme, self.jobs, self.busy = theme, jobs, busy
        self.debounce_ms = DEBOUNCE_MS  # of the step 2 built next (tests set 0)
        self.tabs: TabsPage | None = None
        self._built: tuple[CalcType, ScfInfo] | None = None  # what the step 2 was built for
        self._busy = False
        self._close_confirmed = False
        self.settings = settings

        self.step = set_variant(QLabel(STEP_SETUP), "dialogTitle")
        self.mode_switch = ModeSwitch(self._stored_mode())
        self.mode_switch.mode_changed.connect(self.set_mode)
        self.setup = SetupPage(root, start, busy)
        self.setup.changed.connect(self._update)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.setup)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)
        self.back_button = QPushButton("Voltar")
        self.back_button.clicked.connect(self.back)
        self.continue_button = set_variant(QPushButton("Continuar"), "primary")
        self.continue_button.clicked.connect(self.continue_)
        self.create_button = set_variant(QPushButton("Criar"), "primary")
        self.create_button.clicked.connect(self.request_create)
        for button in (self.cancel_button, self.back_button):
            button.setAutoDefault(False)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for button in (
            self.cancel_button,
            self.back_button,
            self.continue_button,
            self.create_button,
        ):
            buttons.addWidget(button)
        header = QHBoxLayout()
        header.addWidget(self.step, 1)
        header.addWidget(self.mode_switch)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.pages, 1)
        layout.addLayout(buttons)
        self._show_page(self.setup)

    # -- mode ----------------------------------------------------------------------------------
    @property
    def mode(self) -> Mode:
        return self.mode_switch.mode

    def _stored_mode(self) -> Mode:
        stored = self.settings.value(MODE_KEY) if self.settings is not None else None
        for mode in MODES:
            if mode == stored:
                return mode
        return DEFAULT_MODE

    def set_mode(self, mode: Mode) -> None:
        """Show the fields of ``mode`` in step 2 (nothing is rebuilt or lost) and remember it."""
        self.mode_switch.set_mode(mode)
        if self.settings is not None:
            self.settings.setValue(MODE_KEY, mode)
        if self.tabs is not None and self.tabs.mode != mode:
            self.tabs.set_mode(mode)

    # -- pages ---------------------------------------------------------------------------------
    def continue_(self) -> None:
        """Step 2, built again only when the type or the SCF changed (R2.3)."""
        calc_type, scf = self.setup.calc_type, self.setup.scf
        if self.setup.problems() or calc_type is None or scf is None:
            return
        if self._built is None or self._built[0] is not calc_type or self._built[1] is not scf:
            self._build_tabs(calc_type, scf)
        assert self.tabs is not None
        self.tabs.set_target(self.setup.location, self.setup.suffix, self.setup.location_warnings())
        self._show_page(self.tabs)

    def _build_tabs(self, calc_type: CalcType, scf: ScfInfo) -> None:
        if self.tabs is not None:
            self.pages.removeWidget(self.tabs)
            self.tabs.deleteLater()
        self.tabs = TabsPage(
            self.theme, calc_type, scf, self.jobs, self.mode, debounce_ms=self.debounce_ms
        )
        self.tabs.planned.connect(self._update)
        self.pages.addWidget(self.tabs)
        self._built = (calc_type, scf)
        self.setup.show_rebuild_note(False)

    def back(self) -> None:
        self._show_page(self.setup)

    def _show_page(self, page: QWidget) -> None:
        """Only the current page counts for the window's size (``sync_dialog``)."""
        for index in range(self.pages.count()):
            widget = self.pages.widget(index)
            if widget is not None:
                policy = (
                    QSizePolicy.Policy.Preferred if widget is page else QSizePolicy.Policy.Ignored
                )
                widget.setSizePolicy(policy, policy)
        self.pages.setCurrentWidget(page)
        on_setup = page is self.setup
        self.step.setText(STEP_SETUP if on_setup else STEP_FILES)
        self.mode_switch.setVisible(not on_setup)
        self.back_button.setVisible(not on_setup)
        self.continue_button.setVisible(on_setup)
        self.create_button.setVisible(not on_setup)
        (self.continue_button if on_setup else self.create_button).setDefault(True)
        (self.create_button if on_setup else self.continue_button).setDefault(False)
        self._update()

    def on_files_step(self) -> bool:
        return self.tabs is not None and self.pages.currentWidget() is self.tabs

    def _update(self) -> None:
        problems = self.setup.problems()
        self.continue_button.setEnabled(not problems and not self._busy)
        self.continue_button.setToolTip(problems[0] if problems else "")
        built = self._built
        changed = built is not None and (
            built[0] is not self.setup.calc_type or built[1] is not self.setup.scf
        )
        self.setup.show_rebuild_note(changed and self.setup.scf is not None)
        blocking = self.tabs.blocking() if self.tabs is not None else ""
        self.create_button.setEnabled(self.tabs is not None and not blocking and not self._busy)
        self.create_button.setToolTip(blocking)

    # -- create --------------------------------------------------------------------------------
    def request_create(self) -> None:
        tabs, calc_type = self.tabs, self.setup.calc_type
        if tabs is None or calc_type is None or self._busy:
            return
        tabs.flush()  # the plan of what the fields hold now, not of 250 ms ago
        if tabs.blocking():
            return
        self.create_requested.emit(
            CreateRequest(
                self.setup.location, calc_type, self.setup.suffix, tabs.plan, tabs.notes_text()
            )
        )

    def set_busy(self, busy: bool) -> None:
        """While the folder is written: nothing can be edited and the window does not close."""
        self._busy = busy
        self.pages.setEnabled(not busy)
        self.mode_switch.setEnabled(not busy)
        for button in (self.cancel_button, self.back_button):
            button.setEnabled(not busy)
        self._update()

    def close_created(self) -> None:
        """The folder was created: close without asking."""
        self._busy = False
        self._close_confirmed = True
        self.accept()

    # -- closing -------------------------------------------------------------------------------
    def _may_close(self) -> bool:
        if self._busy:
            return False
        if self._close_confirmed:
            return True
        if self.tabs is not None and self.tabs.dirty and not ask_discard(self):
            return False
        self._close_confirmed = True
        return True

    def reject(self) -> None:  # Esc, "Cancelar" and, through closeEvent, the close button
        if self._may_close():
            super().reject()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if not self._may_close():
            if event is not None:
                event.ignore()
            return
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self.setup.shutdown()  # a SCF still being read is dropped
        super().done(result)
