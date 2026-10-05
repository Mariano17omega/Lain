"""The "Projeto" dropdown above the explorer tree (spec 31 R2): "Todos os projetos", the projects
(the first-level folders of the root) and "Criar projeto…".

It only shows names and says what the user picked; the window's ``ProjectController`` decides what a
choice means. Setting the list or the selection from code never emits."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

from .common import set_variant

ALL_TEXT = "Todos os projetos"
CREATE_TEXT = "Criar projeto…"
# What the entries carry: a project's data is its name, which cannot be mistaken for these two
# (a folder name has no NUL).
ALL_KEY = "\0all"
CREATE_KEY = "\0create"
_ROLE = Qt.ItemDataRole.UserRole


class ProjectCombo(QWidget):
    project_chosen = pyqtSignal(object)  # the user picked a project (str) or "Todos" (None)
    create_requested = pyqtSignal()  # the user picked "Criar projeto…"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("projectRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._names: list[str] = []
        self._current: str | None = None  # the last project accepted: what a cancel goes back to
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        self.label = set_variant(QLabel("Projeto"), "panelTitle")
        self.combo = QComboBox()
        self.combo.setObjectName("projectCombo")
        self.combo.setAccessibleName("Projeto")
        self.combo.setToolTip("Mostra só as pastas de um projeto (uma pasta da raiz)")
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.label.setBuddy(self.combo)
        row.addWidget(self.label)
        row.addWidget(self.combo, 1)
        self._rebuild()
        self.combo.activated.connect(self._on_activated)

    # -- what it shows ---------------------------------------------------------------------------
    @property
    def names(self) -> list[str]:
        return list(self._names)

    @property
    def current(self) -> str | None:
        """The selected project, ``None`` for "Todos os projetos"."""
        return self._current

    def texts(self) -> list[str]:
        """The entries as the user sees them (the separators leave out)."""
        return [
            self.combo.itemText(i)
            for i in range(self.combo.count())
            if self.combo.itemData(i, _ROLE) is not None
        ]

    def set_projects(self, names: list[str]) -> None:
        """The list of projects; the selection stays when it is still there, else "Todos"."""
        self._names = list(names)
        self._rebuild()

    def set_current(self, name: str | None) -> None:
        """Select ``name`` (``None``: "Todos"). A name the list does not have yet (the first list
        is still being read) shows anyway."""
        self._current = name
        self._rebuild()

    def restore(self) -> None:
        """Back to the project selected before a "Criar projeto…" that was cancelled."""
        self._rebuild()

    # -- internals -------------------------------------------------------------------------------
    def _rebuild(self) -> None:
        names = self._names
        if self._current is not None and self._current not in names:
            names = sorted(
                [*names, self._current], key=str.casefold
            )  # shown until the list arrives
        combo = self.combo
        combo.clear()
        combo.addItem(ALL_TEXT, ALL_KEY)
        combo.insertSeparator(combo.count())
        for name in names:
            combo.addItem(name, name)
        if names:
            combo.insertSeparator(combo.count())
        combo.addItem(CREATE_TEXT, CREATE_KEY)
        key = ALL_KEY if self._current is None else self._current
        combo.setCurrentIndex(max(combo.findData(key, _ROLE), 0))

    def _on_activated(self, index: int) -> None:
        key = self.combo.itemData(index, _ROLE)
        if key == CREATE_KEY:
            self.create_requested.emit()
            return
        self._current = None if key in (ALL_KEY, None) else str(key)
        self.project_chosen.emit(self._current)
