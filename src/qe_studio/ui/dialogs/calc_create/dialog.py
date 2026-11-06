"""The "Criar cálculo" window (spec 26 R2): step 1 (configuração) and step 2 (arquivos) in one
non-modal dialog, like the sync window's pages.

Nothing is written here: "Criar" asks the controller (``create_requested``), which writes in a
worker and closes the window on success. Esc, the close button and "Cancelar" never create
anything; with fields edited, files edited or notes written they ask first. The "Padrão / Avançado"
switch of step 2 (spec 28) is remembered in QSettings ``calc_create/mode``, and the "Numerar" box of
step 1 (spec 51) in ``calc_create/numbered``, "Sítio no nome" and "Herdar sufixo" (spec 77) in
``calc_create/site_tag`` and ``calc_create/inherit_suffix``, "Gerar fingerprint.md" (spec 80) in
``calc_create/fingerprint``.

"Continuar" is never silent (spec 39 R1): step 1 shows why it does not go on, and a step 2 that
cannot be built is logged and said in a message, with the window left on step 1. Neither is
"Criar": while it is disabled, step 2 shows why in the footer.

"Visualizar 3D" (spec 81) opens one 3D window of the structures being created, which follows the
current step (``structure_preview``) and closes with the window.
"""

from __future__ import annotations

import logging
from functools import partial
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

from ....core.calc_create.fingerprint import Source
from ....core.calc_create.scf_info import ScfInfo, same_scfs
from ....core.calc_create.types import DEFAULT_MODE, MODES, CalcPlan, CalcType, Mode
from ....core.config import JobsConfig
from ....i18n import _
from ...shell.busy import BusyTracker
from ...theme.manager import ThemeManager
from ...widgets.common import set_variant
from .labels import message_label, show_message
from .mode_switch import ModeSwitch
from .setup_page import CHOOSE_SCF, SetupPage
from .structure_preview import PreviewSource, StructurePreview
from .tabs_page import DEBOUNCE_MS, TabsPage

log = logging.getLogger(__name__)

TITLE = _("Criar cálculo")
STEP_SETUP = _("1 · Configuração")
STEP_FILES = _("2 · Arquivos")
MODE_KEY = "calc_create/mode"
NUMBERED_KEY = "calc_create/numbered"
SITE_TAG_KEY = "calc_create/site_tag"
INHERIT_KEY = "calc_create/inherit_suffix"
FINGERPRINT_KEY = "calc_create/fingerprint"
VIEW_TIP = _("Ver em 3D a estrutura do cálculo: a do SCF e a de cada input gerado com outra")


Wanted = tuple[CalcType, tuple[ScfInfo, ...], str]


class CreateRequest(NamedTuple):
    parent: Path
    calc_type: CalcType
    suffix: str
    plan: CalcPlan
    notes: str
    numbered: bool = False  # the place's next number in front of the folder (spec 51)
    inherited: str = ""  # the SCF folder's suffix, after the name (spec 77)
    tag: str = ""  # the site, at the very end of the name (spec 77)
    fingerprint: tuple[Source, ...] | None = None  # the SCFs of ``fingerprint.md``; None: no file
    root: Path | None = None  # what the fingerprint's paths are shown relative to (spec 80)


def ask_discard(parent: QWidget) -> bool:
    answer = QMessageBox.question(
        parent,
        TITLE,
        _("Descartar o que foi preenchido?"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def ask_failed(parent: QWidget, exc: BaseException) -> None:
    """Step 2 could not be built (spec 39 R1.2); the log has the traceback."""
    QMessageBox.warning(
        parent,
        TITLE,
        _(
            "Não foi possível montar os arquivos deste cálculo: {error}. "
            "O log tem o detalhe (Ajuda ▸ Abrir log)."
        ).format(error=str(exc) or type(exc).__name__),
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
        # what the step 2 was built for: the type, the SCFs (one, or step 1's list for a
        # ``multi_scf`` type, spec 79) and, for a type whose file names take it (``uses_name``), the
        # folder's name
        self._built: Wanted | None = None
        self._busy = False
        self._close_confirmed = False
        self.settings = settings

        self.step = set_variant(QLabel(STEP_SETUP), "dialogTitle")
        self.mode_switch = ModeSwitch(self._stored_mode())
        self.mode_switch.mode_changed.connect(self.set_mode)
        self.setup = SetupPage(root, start, busy)
        self.setup.number_check.setChecked(self._stored_numbered())  # before ``_update`` can run
        self.setup.number_check.toggled.connect(self._remember_numbered)
        for key, box in (
            (SITE_TAG_KEY, self.setup.site_check),
            (INHERIT_KEY, self.setup.inherit_check),
            (FINGERPRINT_KEY, self.setup.fingerprint_check),
        ):
            box.setChecked(self._stored_flag(key))
            box.toggled.connect(partial(self._remember_flag, key))
        self.setup.changed.connect(self._update)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.setup)
        self.cancel_button = QPushButton(_("Cancelar"))
        self.cancel_button.clicked.connect(self.reject)
        self.back_button = QPushButton(_("Voltar"))
        self.back_button.clicked.connect(self.back)
        self.continue_button = set_variant(QPushButton(_("Continuar")), "primary")
        self.continue_button.clicked.connect(self.continue_)
        self.create_button = set_variant(QPushButton(_("Criar")), "primary")
        self.create_button.clicked.connect(self.request_create)
        self.create_reason = message_label("error")  # why "Criar" is disabled, on step 2
        self.view_button = QPushButton(_("Visualizar 3D"))
        self.view_button.clicked.connect(self.show_structure)
        self.preview = StructurePreview(theme, settings, self, root=self._root)
        for button in (self.cancel_button, self.back_button, self.view_button):
            button.setAutoDefault(False)

        buttons = QHBoxLayout()
        buttons.addWidget(self.create_reason, 1)
        buttons.addStretch(1)
        for button in (
            self.view_button,
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

    def _stored_flag(self, key: str) -> bool:
        """A box of the name remembered in QSettings (spec 77), unchecked the first time."""
        return self.settings is not None and bool(self.settings.value(key, False, type=bool))

    def _remember_flag(self, key: str, checked: bool) -> None:
        if self.settings is not None:
            self.settings.setValue(key, checked)

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
            setup.location,
            setup.suffix,
            setup.location_warnings(),
            numbered=setup.numbered,
            inherited=setup.inherited,
            use_tag=setup.site_tag,
            fingerprint_root=setup.root if setup.fingerprint else None,
        )
        self._show_page(self.tabs)

    def _wanted(self) -> Wanted | None:
        """What step 2 would be built for now (None: the type or the SCF is not chosen yet)."""
        calc_type, scf = self.setup.calc_type, self.setup.scf
        if calc_type is None or scf is None:
            return None
        scfs = self.setup.scfs or (scf,)
        return calc_type, scfs, self.setup.suffix if calc_type.uses_name else ""

    def _stale(self, wanted: Wanted) -> bool:
        built = self._built
        return (
            built is None
            or built[0] is not wanted[0]
            or not same_scfs(built[1], wanted[1])
            or built[2] != wanted[2]
        )

    def _build_tabs(self, calc_type: CalcType, scfs: tuple[ScfInfo, ...], suffix: str) -> bool:
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
                scfs[0],
                self.jobs,
                self.mode,
                debounce_ms=self.debounce_ms,
                name=suffix,
                scfs=scfs if calc_type.multi_scf else (),
                root=self.setup.root,
            )
        except Exception as exc:  # noqa: BLE001 - shown and logged, never a silent click
            log.exception("action: building step 2 of a new %s calculation failed", calc_type.id)
            self.setup.show_rebuild_note(False)
            ask_failed(self, exc)
            self._update()
            return False
        self.tabs.planned.connect(self._update)
        self.pages.addWidget(self.tabs)
        self._built = (calc_type, scfs, suffix)
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
        show_message(self.create_reason, blocking if self.on_files_step() else "")
        source, reason = self._preview_source()
        self.view_button.setEnabled(source is not None)
        self.view_button.setToolTip(reason)
        if source is not None:
            self.preview.refresh(*source)

    # -- Visualizar 3D (spec 81) ---------------------------------------------------------------
    def _preview_source(self) -> tuple[PreviewSource | None, str]:
        """What the 3D window shows now (step 2: its plan; step 1: the SCF or the list), or why
        there is nothing."""
        if self.on_files_step():
            assert self.tabs is not None
            return (self.tabs.scf, self.tabs.plan, self.tabs.scfs), VIEW_TIP
        scf, scfs = self.setup.scf, self.setup.scfs
        if scf is None:
            return None, CHOOSE_SCF
        if all(each.crystal is None for each in scfs or (scf,)):
            return None, scf.structure_problem or CHOOSE_SCF
        return (scf, None, scfs), VIEW_TIP

    def show_structure(self) -> None:
        source, _reason = self._preview_source()
        if source is not None:
            self.preview.open(*source)

    def _root(self) -> Path:
        return self.setup.root

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
                setup.inherited,
                tabs.plan.folder_tag if setup.site_tag else "",
                tabs.fingerprint_sources(),
                setup.root,
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
        self.preview.close()  # the 3D window goes with the dialog (spec 81 R3.3)
        self.setup.shutdown()  # a SCF still being read is dropped, and the fields' files
        if self.tabs is not None:
            self.tabs.shutdown()
        super().done(result)
