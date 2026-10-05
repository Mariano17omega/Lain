"""Helpers of the project tests (spec 31): the dropdown as the user drives it."""

from pathlib import Path

from qe_studio.core.config import LoadedConfig, parse_config

ALL = "Todos os projetos"
CREATE = "Criar projeto…"


def config_of(root: Path) -> LoadedConfig:
    return LoadedConfig(parse_config({"paths": {"local_root": str(root)}}), None)


def pick(window, text: str) -> None:
    """What the user does with the dropdown: choose the entry called ``text``."""
    combo = window.explorer.projects.combo
    index = combo.findText(text)
    assert index >= 0, f"{text!r} is not in {window.explorer.projects.texts()}"
    combo.setCurrentIndex(index)
    combo.activated.emit(index)


def current_text(window) -> str:
    return window.explorer.projects.combo.currentText()
