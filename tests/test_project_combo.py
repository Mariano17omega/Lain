"""Spec 31 R2: the "Projeto" dropdown widget on its own: entries, selection, what it emits."""

import pytest
from PyQt6.QtCore import Qt

from project_helpers import ALL, CREATE
from qe_studio.ui.widgets.project_combo import ProjectCombo


@pytest.fixture
def combo(qtbot):
    widget = ProjectCombo()
    qtbot.addWidget(widget)
    return widget


def activate(combo: ProjectCombo, text: str) -> None:
    index = combo.combo.findText(text)
    combo.combo.setCurrentIndex(index)
    combo.combo.activated.emit(index)


def test_without_projects_it_offers_all_and_create(combo):
    assert combo.texts() == [ALL, CREATE]
    assert combo.combo.currentText() == ALL and combo.current is None


def test_the_entries_are_all_then_the_projects_then_create(combo):
    combo.set_projects(["ilita", "outro"])
    assert combo.texts() == [ALL, "ilita", "outro", CREATE]
    assert combo.names == ["ilita", "outro"]
    # separators between the three groups
    kinds = [combo.combo.itemData(i, Qt.ItemDataRole.UserRole) for i in range(combo.combo.count())]
    assert kinds.count(None) == 2


def test_setting_from_code_never_emits(qtbot, combo):
    chosen = []
    combo.project_chosen.connect(chosen.append)
    combo.create_requested.connect(lambda: chosen.append("create"))
    combo.set_projects(["ilita", "outro"])
    combo.set_current("outro")
    combo.set_current(None)
    assert chosen == [] and combo.combo.currentText() == ALL


def test_the_user_picks_a_project_all_or_create(combo):
    chosen = []
    combo.project_chosen.connect(chosen.append)
    asked = []
    combo.create_requested.connect(lambda: asked.append(True))
    combo.set_projects(["ilita", "outro"])
    activate(combo, "outro")
    assert chosen == ["outro"] and combo.current == "outro"
    activate(combo, ALL)
    assert chosen == ["outro", None] and combo.current is None
    activate(combo, "ilita")
    activate(combo, CREATE)
    assert asked == [True]
    assert combo.current == "ilita"  # create is not a project: the choice stays
    combo.restore()  # a cancelled dialog puts the dropdown back
    assert combo.combo.currentText() == "ilita"


def test_a_project_the_list_lacks_still_shows_until_the_list_arrives(combo):
    combo.set_current("ilita")  # restored from the settings before the first list
    assert combo.combo.currentText() == "ilita"
    combo.set_projects(["ilita", "outro"])
    assert combo.combo.currentText() == "ilita"
    combo.set_projects(["outro"])  # the list says it is gone: the caller decides what to do
    combo.set_current(None)
    assert combo.combo.currentText() == ALL and "ilita" not in combo.texts()


def test_the_selection_survives_a_new_list(combo):
    combo.set_projects(["ilita"])
    combo.set_current("ilita")
    combo.set_projects(["ilita", "outro", "terceiro"])
    assert combo.combo.currentText() == "ilita"


def test_it_is_a_labelled_named_control(combo):
    assert combo.label.text() == "Projeto" and combo.label.buddy() is combo.combo
    assert combo.combo.objectName() == "projectCombo" and combo.objectName() == "projectRow"
