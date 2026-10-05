"""Name of a new project (spec 31 R4): the folder ``Criar projeto…`` makes in the root. The name is
checked as it is typed (``core/projects.validate_project_name``); "Criar" waits for a clean one."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.projects import validate_project_name
from ..widgets.common import set_variant


class NewProjectDialog(QDialog):
    def __init__(
        self,
        existing: list[str],
        hidden_dirs: list[str] | tuple[str, ...] = (),
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.existing, self.hidden_dirs = list(existing), list(hidden_dirs)
        self.name: str | None = None
        self.setWindowTitle("Criar projeto")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(set_variant(QLabel("Criar projeto"), "dialogTitle"))
        layout.addWidget(set_variant(QLabel("Nome do projeto"), "dialogText"))
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(380)
        self.edit.setAccessibleName("Nome do projeto")
        layout.addWidget(self.edit)
        self.error = set_variant(QLabel(), "dialogError")
        self.error.hide()
        layout.addWidget(self.error)
        note = set_variant(
            QLabel("O nome será o nome da pasta, criada na pasta raiz."), "dialogText"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.create_button = set_variant(QPushButton("Criar"), "primary")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.create_button)
        layout.addLayout(row)
        self.edit.textChanged.connect(self._check)
        self._check()

    def problems(self) -> list[str]:
        return validate_project_name(self.edit.text(), self.existing, self.hidden_dirs)

    def _check(self) -> None:
        problems = self.problems()
        self.create_button.setEnabled(not problems)
        # Nothing typed yet is not an error to show: "Criar" just waits.
        if problems and self.edit.text().strip():
            self.error.setText(problems[0])
            self.error.show()
        else:
            self.error.hide()

    def accept(self) -> None:
        if self.problems():  # Enter in the field reaches here too
            return
        self.name = self.edit.text().strip()
        super().accept()


def ask_new_project(
    parent: QWidget, existing: list[str], hidden_dirs: list[str] | tuple[str, ...] = ()
) -> str | None:
    """The name of the project to create, or None if cancelled."""
    dialog = NewProjectDialog(existing, hidden_dirs, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    name = dialog.name if accepted else None
    dialog.deleteLater()
    return name
