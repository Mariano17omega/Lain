"""Spec 18 R5: the empty states (no config.yaml, project folder gone) and the first config."""

import hashlib
import os
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMessageBox

from grid_helpers import tree_names
from qe_studio.core.config import LoadedConfig, load_config
from qe_studio.core.config_template import template_text, with_local_root
from qe_studio.ui import first_run as first_run_module
from qe_studio.ui.first_run import AFTER_EDIT, TEMPORARY

CONFIRM = "ask_create_with_folder"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A home of its own (the default ``local_root`` is ``~/qe_simulations``) and a cwd with no
    config.yaml, so the lookup finds nothing but what a test creates."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.delenv("QE_STUDIO_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    return folder


@pytest.fixture
def first_run_window(window_factory, home):
    loaded = load_config(None)
    assert loaded.first_run
    return window_factory(loaded=loaded)


@pytest.fixture
def missing_root_window(window_factory, home, tmp_path):
    config = tmp_path / "mine.yaml"
    config.write_text(with_local_root(template_text(), tmp_path / "gone"), encoding="utf-8")
    return window_factory(loaded=load_config(config)), config


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def click(window, label: str) -> None:
    window.first_run.overlay.buttons[label].click()


def created_config() -> Path:
    return Path(os.environ["XDG_CONFIG_HOME"]) / "qe-studio" / "config.yaml"


# -- no config.yaml ---------------------------------------------------------------------------
def test_no_config_shows_the_welcome_state(first_run_window):
    window = first_run_window
    overlay = window.first_run.overlay
    assert window.first_run.state == "first_run"
    assert overlay.isVisible()
    assert overlay.title.text() == "Bem-vindo ao Lain"
    assert "Nenhum config.yaml encontrado" in overlay.text.text()
    assert list(overlay.buttons) == ["Criar config…", "Escolher pasta…"]


def test_the_overlay_covers_the_splitter(first_run_window):
    window = first_run_window
    assert window.first_run.overlay.geometry() == window.splitter.geometry()
    window.resize(1000, 700)
    assert window.first_run.overlay.geometry() == window.splitter.geometry()


def test_a_window_with_a_valid_project_has_no_overlay(main_window):
    assert main_window.first_run.state is None
    assert not main_window.first_run.overlay.isVisible()


def test_choose_folder_creates_the_config_with_that_project(
    qtbot, first_run_window, demo_project, monkeypatch
):
    window = first_run_window
    monkeypatch.setattr(first_run_module, "choose_folder", lambda parent: demo_project)
    monkeypatch.setattr(first_run_module, CONFIRM, lambda parent, folder: True)
    click(window, "Escolher pasta…")
    path = created_config()
    assert path.is_file()
    assert load_config(path).config.paths.local_root == demo_project
    assert window.loaded.path == path and not window.loaded.first_run
    assert window.root == demo_project
    assert not window.first_run.overlay.isVisible()
    qtbot.waitUntil(lambda: "01_relax" in tree_names(window), timeout=5000)  # the model loads
    assert window.files.folder == demo_project


def test_choose_folder_does_nothing_when_cancelled_or_refused(first_run_window, monkeypatch):
    window = first_run_window
    monkeypatch.setattr(first_run_module, "choose_folder", lambda parent: None)
    click(window, "Escolher pasta…")
    assert not created_config().exists()
    monkeypatch.setattr(first_run_module, "choose_folder", lambda parent: Path("/tmp"))
    monkeypatch.setattr(first_run_module, CONFIRM, lambda parent, folder: False)
    click(window, "Escolher pasta…")
    assert not created_config().exists()
    assert window.first_run.overlay.isVisible()


def test_create_config_writes_the_template_and_opens_it(
    qtbot, first_run_window, fake_apps, launched, monkeypatch
):
    window = first_run_window
    asked = []
    monkeypatch.setattr(
        first_run_module, "ask_create_config", lambda parent, path: asked.append(path) or True
    )
    click(window, "Criar config…")
    path = created_config()
    assert asked == [path]
    assert path.read_text(encoding="utf-8") == template_text()
    assert window.workspace.widget_for(str(path)) is not None  # the viewer tab
    assert any(path.as_uri() in args for _program, args, _cwd in launched)  # the external editor
    assert window.status.message.text() == AFTER_EDIT
    assert window.first_run.overlay.isVisible()  # until the user reloads


def test_reloading_after_editing_leaves_the_welcome_state(
    first_run_window, fake_apps, launched, monkeypatch
):
    window = first_run_window
    monkeypatch.setattr(first_run_module, "ask_create_config", lambda parent, path: True)
    click(window, "Criar config…")
    window._actions["config.reload"].trigger()
    assert window.loaded.path == created_config() and not window.loaded.first_run
    # The template's local_root (~/qe_simulations) is not in the temporary home: the next state.
    assert window.first_run.state == "missing_root"
    (window.root).mkdir(parents=True)
    window._actions["config.reload"].trigger()
    assert window.first_run.state is None and not window.first_run.overlay.isVisible()


def test_refusing_the_confirmation_creates_nothing(first_run_window, launched, monkeypatch):
    monkeypatch.setattr(first_run_module, "ask_create_config", lambda parent, path: False)
    click(first_run_window, "Criar config…")
    assert not created_config().exists() and launched == []


def test_open_config_without_a_config_offers_to_create_one(
    first_run_window, fake_apps, launched, monkeypatch
):
    window = first_run_window
    boxes = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a: boxes.append(a)))
    monkeypatch.setattr(first_run_module, "ask_create_config", lambda parent, path: True)
    window._actions["config.open"].trigger()
    assert created_config().is_file() and boxes == []  # not the old "copy the example" message


def test_an_existing_user_config_is_opened_not_overwritten(
    first_run_window, fake_apps, launched, monkeypatch
):
    path = created_config()
    path.parent.mkdir(parents=True)
    path.write_text("# mine\n", encoding="utf-8")
    before = digest(path)
    monkeypatch.setattr(
        first_run_module, "ask_create_config", lambda *a: pytest.fail("must not ask")
    )
    click(first_run_window, "Criar config…")
    assert digest(path) == before


# -- config exists, project folder does not --------------------------------------------------
def test_a_missing_project_folder_shows_its_own_state(missing_root_window, tmp_path):
    window, _config = missing_root_window
    overlay = window.first_run.overlay
    assert window.first_run.state == "missing_root" and overlay.isVisible()
    assert f"A pasta raiz não foi encontrada: {tmp_path / 'gone'}" in overlay.text.text()
    assert list(overlay.buttons) == ["Abrir config", "Escolher pasta…"]


def test_choosing_a_folder_there_is_temporary_and_leaves_the_config_alone(
    qtbot, missing_root_window, demo_project, monkeypatch
):
    window, config = missing_root_window
    before = digest(config)
    monkeypatch.setattr(first_run_module, "choose_folder", lambda parent: demo_project)
    click(window, "Escolher pasta…")
    assert digest(config) == before  # PRD §6: Lain never rewrites an existing config
    assert window.root == demo_project and window.loaded.path == config
    assert not window.first_run.overlay.isVisible()
    assert window.status.message.text() == TEMPORARY
    qtbot.waitUntil(lambda: "01_relax" in tree_names(window), timeout=5000)
    # The next reload goes back to what the file says.
    window._actions["config.reload"].trigger()
    assert window.root != demo_project and window.first_run.state == "missing_root"
    assert digest(config) == before


def test_open_config_opens_it_in_the_viewer_and_the_editor(
    missing_root_window, fake_apps, launched
):
    window, config = missing_root_window
    click(window, "Abrir config")
    assert window.workspace.widget_for(str(config)) is not None
    assert any(config.as_uri() in args for _program, args, _cwd in launched)


def test_session_root_does_not_break_a_config_with_a_valid_root(main_window, demo_project):
    other = demo_project / "01_relax"
    before = main_window.loaded.path
    main_window.use_session_root(other)
    assert main_window.root == other and main_window.loaded.path == before
    assert main_window.files.folder == other
    assert main_window.first_run.state is None


def test_the_built_loaded_config_is_not_a_first_run(main_window):
    assert not LoadedConfig(main_window.config, None).first_run
