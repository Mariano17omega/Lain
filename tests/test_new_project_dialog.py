"""Spec 31 R4: the "Criar projeto" dialog: live validation, "Criar" only for a clean name."""

import pytest
from PyQt6.QtWidgets import QDialog

from qe_studio.ui.dialogs import new_project
from qe_studio.ui.dialogs.new_project import NewProjectDialog, ask_new_project


@pytest.fixture
def dialog(qtbot):
    window = NewProjectDialog(["ilita", "outro"], ["tmp", "*.save"])
    qtbot.addWidget(window)
    window.show()
    return window


def test_it_opens_waiting_for_a_name(dialog):
    assert dialog.windowTitle() == "Criar projeto"
    assert dialog.edit.text() == "" and dialog.edit.accessibleName() == "Nome do projeto"
    assert not dialog.create_button.isEnabled()
    assert dialog.error.isHidden()  # nothing typed is not an error to show


def test_a_clean_name_enables_create(dialog):
    dialog.edit.setText("novo-projeto")
    assert dialog.create_button.isEnabled() and dialog.error.isHidden()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted and dialog.name == "novo-projeto"


@pytest.mark.parametrize(
    "text, reason",
    [
        ("a/b", "Use só letras"),
        (".oculto", "ponto"),
        ("plots", "reservado"),
        ("tmp", "reservado"),
        ("Ilita", "Já existe um projeto"),
        ("ilita", "Já existe um projeto"),
    ],
)
def test_a_bad_name_says_why_and_blocks_create(dialog, text, reason):
    dialog.edit.setText(text)
    assert not dialog.create_button.isEnabled()
    assert not dialog.error.isHidden() and reason in dialog.error.text()
    dialog.accept()  # Enter in the field: nothing happens
    assert dialog.name is None and dialog.result() != QDialog.DialogCode.Accepted


def test_the_message_follows_the_typing(dialog):
    dialog.edit.setText("ilita")
    assert not dialog.error.isHidden()
    dialog.edit.setText("ilita2")
    assert dialog.error.isHidden() and dialog.create_button.isEnabled()
    dialog.edit.setText("")
    assert dialog.error.isHidden() and not dialog.create_button.isEnabled()


def test_the_name_is_trimmed(dialog):
    dialog.edit.setText("  novo ")
    assert dialog.create_button.isEnabled()
    dialog.accept()
    assert dialog.name == "novo"


def test_ask_returns_the_name_or_none(qtbot, monkeypatch):
    def fake_exec(accepted: bool, typed: str):
        def run(self):
            self.edit.setText(typed)
            if accepted:
                self.accept()
                return QDialog.DialogCode.Accepted
            self.reject()
            return QDialog.DialogCode.Rejected

        return run

    monkeypatch.setattr(QDialog, "exec", fake_exec(True, "novo"))
    assert ask_new_project(None, ["ilita"]) == "novo"
    monkeypatch.setattr(QDialog, "exec", fake_exec(False, "novo"))
    assert ask_new_project(None, ["ilita"]) is None
    assert new_project.ask_new_project is ask_new_project
