"""Spec end R2: which language the program starts in, and Qt's own texts in it."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QMessageBox

from qe_studio import i18n
from qe_studio.core.language import (
    ENV_LANGUAGE,
    ENV_LANGUAGE_ALIAS,
    changes_on_restart,
    configured_language,
    pinned_language,
    resolve_language,
    startup_language,
)
from qe_studio.ui.language import install_qt_translator, install_startup_language, restart_notice


@pytest.fixture(autouse=True)
def source_language():
    yield
    i18n.install("pt_BR")


@pytest.mark.parametrize(
    ("setting", "system", "language"),
    [
        ("pt_BR", "en_US", "pt_BR"),
        ("en", "pt_BR", "en"),
        ("auto", "pt_BR", "pt_BR"),
        ("auto", "pt_PT", "pt_BR"),
        ("auto", "pt", "pt_BR"),
        ("auto", "en_US", "en"),
        ("auto", "de_DE", "en"),
        ("auto", "C", "en"),
        ("auto", "", "en"),
    ],
)
def test_auto_follows_the_system(setting, system, language):
    assert resolve_language(setting, system) == language


@pytest.mark.parametrize(
    ("environ", "pinned"),
    [
        ({}, None),
        ({ENV_LANGUAGE: "en"}, "en"),
        ({ENV_LANGUAGE: "pt_BR"}, "pt_BR"),
        ({ENV_LANGUAGE_ALIAS: "en"}, "en"),
        ({ENV_LANGUAGE: "pt_BR", ENV_LANGUAGE_ALIAS: "en"}, "pt_BR"),  # the internal name wins
        ({ENV_LANGUAGE: "en_US.UTF-8"}, "en"),
        ({ENV_LANGUAGE: "pt_PT"}, "pt_BR"),
        ({ENV_LANGUAGE: "auto"}, None),
        ({ENV_LANGUAGE: "  "}, None),
    ],
)
def test_an_environment_variable_pins_the_language(environ, pinned):
    assert pinned_language(environ) == pinned


def write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("text", "setting"),
    [
        ("ui:\n  language: en\n", "en"),
        ("ui:\n  language: pt_BR\n", "pt_BR"),
        ("ui:\n  language: auto\n", "auto"),
        ("ui:\n  language: fr\n", "auto"),
        ("ui:\n  theme: dark\n", "auto"),
        ("ui: 3\n", "auto"),
        ("- a list\n", "auto"),
        ("ui: [unclosed\n", "auto"),
        ("", "auto"),
    ],
)
def test_the_config_file_is_read_leniently(tmp_path, text, setting):
    assert configured_language(write_config(tmp_path, text)) == setting


def test_a_missing_or_binary_config_means_auto(tmp_path):
    assert configured_language(None) == "auto"
    assert configured_language(tmp_path / "missing.yaml") == "auto"
    binary = tmp_path / "binary.yaml"
    binary.write_bytes(b"\xff\xfe\x00")
    assert configured_language(binary) == "auto"


def test_startup_language_order(tmp_path):
    path = write_config(tmp_path, "ui:\n  language: en\n")
    assert startup_language(path, {}, "pt_BR") == "en"  # the file beats the system
    assert (
        startup_language(path, {ENV_LANGUAGE: "pt_BR"}, "en_US") == "pt_BR"
    )  # the variable, the file
    assert startup_language(None, {}, "pt_BR") != "" and startup_language(None, {}, "de_DE") == "en"
    missing = tmp_path / "missing.yaml"
    assert startup_language(missing, {}, "pt_BR") == "pt_BR"  # reported later by load_config


def test_install_startup_language_follows_the_command_line(tmp_path):
    path = write_config(tmp_path, "ui:\n  language: en\n")
    assert install_startup_language(["--config", str(path), "--verbose"], environ={}) == "en"
    assert i18n.current_language() == "en"
    assert install_startup_language([], environ={ENV_LANGUAGE: "pt_BR"}) == "pt_BR"
    assert i18n.current_language() == "pt_BR"


@pytest.mark.parametrize(
    ("setting", "current", "pinned", "changes"),
    [
        ("en", "pt_BR", False, True),
        ("pt_BR", "pt_BR", False, False),
        ("en", "en", False, False),
        ("en", "pt_BR", True, False),  # the variable fixes the language: the file does not matter
    ],
)
def test_the_notice_asks_for_a_restart_only_when_the_language_would_change(
    setting, current, pinned, changes
):
    environ = {ENV_LANGUAGE: current} if pinned else {}
    assert changes_on_restart(setting, current, environ, "de_DE") is changes


def test_restart_notice_text(monkeypatch):
    monkeypatch.delenv(ENV_LANGUAGE, raising=False)
    monkeypatch.delenv(ENV_LANGUAGE_ALIAS, raising=False)
    i18n.install("pt_BR")
    assert restart_notice("en") == "O idioma muda ao reiniciar o Lain."
    assert restart_notice("pt_BR") == ""


def test_qt_standard_buttons_follow_the_language(qapp):
    """Qt's source language is English: Portuguese needs its own catalog (shipped by PyQt6)."""

    def buttons():
        box = QMessageBox()
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        texts = [b.text().replace("&", "") for b in box.buttons()]
        box.deleteLater()
        return texts

    try:
        if not install_qt_translator(qapp, "pt_BR"):
            pytest.skip("Qt's Portuguese translation is not installed")
        assert buttons() == ["Sim", "Não"]
        install_qt_translator(qapp, "en")
        assert buttons() == ["Yes", "No"]
    finally:
        install_qt_translator(qapp, "en")
