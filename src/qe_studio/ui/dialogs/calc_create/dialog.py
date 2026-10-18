"""The "Criar cálculo" window (spec 26 R2): step 1 (configuração) and step 2 (arquivos) in one
non-modal dialog, like the sync window's pages.

Nothing is written here: "Criar" asks the controller (``create_requested``), which writes in a
worker and closes the window on success. Esc, the close button and "Cancelar" never create
anything; with fields edited, files edited or notes written they ask first. The "Padrão / Avançado"
switch of step 2 (spec 28) is remembered in QSettings ``calc_create/mode``, and the "Numerar" box of
step 1 (spec 51) in ``calc_create/numbered``.

"Continuar" is never silent (spec 39 R1): step 1 shows why it does not go on, and a step 2 that
cannot be built is logged and said in a message, with the window left on step 1.
"""

from __future__ import annotations

import logging
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
from .setup_page import CHOOSE_SCF, SetupPage
from .tabs_page import DEBOUNCE_MS, TabsPage

log = logging.getLogger(__name__)

TITLE = "Criar cálculo"
STEP_SETUP = "1 · Configuração"
STEP_FILES = "2 · Arquivos"
MODE_KEY = "calc_create/mode"
NUMBERED_KEY = "calc_create/numbered"


class CreateRequest(NamedTuple):
    parent: Path
    calc_type: CalcType
    suffix: str
    plan: CalcPlan
    notes: str
    numbered: bool = False  # the place's next number in front of the folder (spec 51)


def ask_discard(parent: QWidget) -> bool:
    answer = QMessageBox.question(
        parent,
        TITLE,
        "Descartar o que foi preenchido?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def ask_failed(parent: QWidget, exc: BaseException) -> None:
    """Step 2 could not be built (spec 39 R1.2); the log has the traceback."""
    QMessageBox.warning(
        parent,
        TITLE,
        f"Não foi possível montar os arquivos deste cálculo: {str(exc) or type(exc).__name__}. "
        "O log tem o detalhe (Ajuda ▸ Abrir log).",
    )


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
        """``settings``: where the mode and "Numerar" are remembered (None: not remembered,
        ``padrao`` and unchecked)."""
        super().__init__(parent)
        self.setObjectName("calcCreateDialog")
        self.setWindowTitle(TITLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(960, 640)
        self.theme, self.jobs, self.busy = theme, jobs, busy
        self.debounce_ms = DEBOUNCE_MS  # of the step 2 built next (tests set 0)
        self.tabs: TabsPage | None = None
        # what the step 2 was built for: the type, the SCF and, for a type whose file names take it
        # (``uses_name``), the folder's name
        self._built: tuple[CalcType, ScfInfo, str] | None = None
        self._busy = False
        self._close_confirmed = False
        self.settings = settings

        self.step = set_variant(QLabel(STEP_SETUP), "dialogTitle")
        self.mode_switch = ModeSwitch(self._stored_mode())
        self.mode_switch.mode_changed.connect(self.set_mode)
        self.setup = SetupPage(root, start, busy)
        self.setup.number_check.setChecked(self._stored_numbered())  # before ``_update`` can run
        self.setup.number_check.toggled.connect(self._remember_numbered)
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

    # -- numbering (spec 51) -------------------------------------------------------------------
    def _stored_numbered(self) -> bool:
        if self.settings is None:
            return False
        return bool(self.settings.value(NUMBERED_KEY, False, type=bool))

    def _remember_numbered(self, checked: bool) -> None:
        if self.settings is not None:
            self.settings.setValue(NUMBERED_KEY, checked)

    # -- pages ---------------------------------------------------------------------------------
    def continue_(self) -> None:
        """Step 2, built again only when the type or the SCF changed (R2.3), or the folder's name
        for a type whose file names take it (spec 29)."""
        wanted, problems = self._wanted(), self.setup.problems()
        if problems or wanted is None:
            self.setup.show_reason(problems[0] if problems else CHOOSE_SCF)
            return
        if self._stale(wanted) and not self._build_tabs(*wanted):
            return
        assert self.tabs is not None
        setup = self.setup
        self.tabs.set_target(
            setup.location, setup.suffix, setup.location_warnings(), numbered=setup.numbered
        )
        self._show_page(self.tabs)

    def _wanted(self) -> tuple[CalcType, ScfInfo, str] | None:
        """What step 2 would be built for now (None: the type or the SCF is not chosen yet)."""
        calc_type, scf = self.setup.calc_type, self.setup.scf
        if calc_type is None or scf is None:
            return None
        return calc_type, scf, self.setup.suffix if calc_type.uses_name else ""

    def _stale(self, wanted: tuple[CalcType, ScfInfo, str]) -> bool:
        built = self._built
        return (
            built is None
            or built[0] is not wanted[0]
            or built[1] is not wanted[1]
            or built[2] != wanted[2]
        )

    def _build_tabs(self, calc_type: CalcType, scf: ScfInfo, suffix: str) -> bool:
        """A new step 2 (the old one and its edits are dropped). False when it could not be built:
        logged, said in a message, and the window stays on step 1 with no step 2."""
        if self.tabs is not None:
            self.tabs.shutdown()
            self.pages.removeWidget(self.tabs)
            self.tabs.deleteLater()
            self.tabs, self._built = None, None
        try:
            self.tabs = TabsPage(
                self.theme,
                calc_type,
                scf,
                self.jobs,
                self.mode,
                debounce_ms=self.debounce_ms,
                name=suffix,
            )
        except Exception as exc:  # noqa: BLE001 - shown and logged, never a silent click
            log.exception("building step 2 of a new %s calculation failed", calc_type.id)
            self.setup.show_rebuild_note(False)
            ask_failed(self, exc)
            self._update()
            return False
        self.tabs.planned.connect(self._update)
        self.pages.addWidget(self.tabs)
        self._built = (calc_type, scf, suffix)
        self.setup.show_rebuild_note(False)
        return True

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
        wanted = self._wanted()
        self.setup.show_rebuild_note(
            self._built is not None and wanted is not None and self._stale(wanted),
            lose_edits=self.tabs is not None and self.tabs.has_edits,
        )
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
        setup = self.setup
        self.create_requested.emit(
            CreateRequest(
                setup.location,
                calc_type,
                setup.suffix,
                tabs.plan,
                tabs.notes_text(),
                setup.numbered,
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
        self.setup.shutdown()  # a SCF still being read is dropped, and the fields' files
        if self.tabs is not None:
            self.tabs.shutdown()
        super().done(result)
