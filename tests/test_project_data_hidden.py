"""The root's settings folder is never shown, listed, detected nor taken as a project (spec 48 R5):
the leading-dot rule already hides it, and these tests make that a contract for its name."""

import json
from pathlib import Path

import pytest

from grid_helpers import names, show_folder, tree_names
from project_helpers import ALL, CREATE, config_of
from qe_studio.core.calculations.listing import FolderListing
from qe_studio.core.detection import detect_folder
from qe_studio.core.folder_index import list_folders
from qe_studio.core.paths import count_entries
from qe_studio.core.project_data import (
    COMPOUNDS_FILE,
    FOLDERS_FILE,
    GRIDS_FILE,
    NAVIGATION_FILE,
    PROJECT_DATA_DIR,
)
from qe_studio.core.projects import (
    ProjectError,
    create_project,
    list_projects,
    validate_project_name,
)
from qe_studio.ui.dialogs.new_project import NewProjectDialog

FAVORITE = "ilita/Analise_2"


def settings_folder(root: Path) -> Path:
    """A real ``.lain`` with the four files, as a copy of a used root has it."""
    folder = root / PROJECT_DATA_DIR
    folder.mkdir()
    files = {
        FOLDERS_FILE: {"version": 2, "folders": {"ilita/Analise_1/Bandas": {"labels": ["G", "X"]}}},
        GRIDS_FILE: {"version": 1, "grids": {"Vazia": {"rows": 1, "cols": 1, "cells": []}}},
        COMPOUNDS_FILE: {"version": 1, "compounds": {"Al O": {"formula": "AlO", "atoms": [1]}}},
        NAVIGATION_FILE: {
            "version": 1,
            "projects": {".": {"favorites": [FAVORITE], "recents": []}},
        },
    }
    for name, data in files.items():
        (folder / name).write_text(json.dumps(data), encoding="utf-8")
    return folder


@pytest.fixture
def raiz_lain(raiz):
    settings_folder(raiz)
    return raiz


def test_the_core_lists_never_see_it(raiz):
    before = (
        list_projects(raiz, []),
        list_folders(raiz, []),
        count_entries(raiz),
        FolderListing.scan(raiz),
        detect_folder(raiz),
    )
    settings_folder(raiz)
    projects = list_projects(raiz, [])
    assert [p.name for p in projects] == ["ilita", "outro"]
    assert PROJECT_DATA_DIR not in {p.name for p in list_folders(raiz, [])}
    assert list_folders(raiz, []) == before[1]
    assert count_entries(raiz) == before[2]
    assert FolderListing.scan(raiz) == before[3]  # IGNORED_SUBDIRS: no PDOS read below it
    assert [r.module.kind for r in detect_folder(raiz)] == [r.module.kind for r in before[4]]
    assert projects == before[0]


def test_it_is_no_project_name(raiz_lain):
    assert validate_project_name(PROJECT_DATA_DIR, []) == ["O nome não pode começar com ponto"]
    before = sorted(p.name for p in (raiz_lain / PROJECT_DATA_DIR).iterdir())
    with pytest.raises(ProjectError, match="ponto"):
        create_project(raiz_lain, PROJECT_DATA_DIR)
    assert sorted(p.name for p in (raiz_lain / PROJECT_DATA_DIR).iterdir()) == before
    with pytest.raises(ProjectError):
        create_project(raiz_lain / "outro", PROJECT_DATA_DIR)  # nor inside a project
    assert not (raiz_lain / "outro" / PROJECT_DATA_DIR).exists()


def test_the_new_project_dialog_refuses_it(qtbot):
    dialog = NewProjectDialog(["ilita", "outro"], [])
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.edit.setText(PROJECT_DATA_DIR)
    assert not dialog.create_button.isEnabled()
    assert "ponto" in dialog.error.text()


def test_the_window_shows_it_nowhere(qtbot, window_factory, raiz_lain):
    window = window_factory(config_of(raiz_lain), follow_root=True)
    qtbot.waitUntil(lambda: window.project.names != [], timeout=5000)
    assert window.project.names == ["ilita", "outro"]
    assert window.explorer.projects.texts() == [ALL, "ilita", "outro", CREATE]
    qtbot.waitUntil(lambda: tree_names(window) == ["ilita", "outro", "plots"], timeout=5000)
    show_folder(qtbot, window, raiz_lain, up=False)
    assert PROJECT_DATA_DIR not in names(window.files) and "ilita" in names(window.files)
    palette = window.command_palette
    palette._ensure_index()
    qtbot.waitUntil(lambda: palette._folders is not None, timeout=5000)
    keys = [r.key for r in palette.rows_for("/") + palette.rows_for("") + palette.rows_for(">")]
    labels = [r.label for r in palette.rows_for("/")]
    assert keys and not any(PROJECT_DATA_DIR in key for key in keys)
    assert not any(PROJECT_DATA_DIR in label for label in labels)
    # The window read its stores from there: the favorite of the copied root is back.
    assert window.navigation_store.favorites() == [raiz_lain / FAVORITE]
    assert window.memory.labels(raiz_lain / "ilita" / "Analise_1" / "Bandas") == ["G", "X"]
