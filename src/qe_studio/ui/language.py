"""The program's language at startup, and Qt's own texts in it (spec end R1.3, R2).

``install_startup_language`` runs before the application modules are imported (``__main__``): the
texts are translated while the modules load. Importing this module loads no module with texts.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence

from PyQt6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

from .. import i18n
from ..core.language import changes_on_restart, startup_language
from ..i18n import _

_qt_translator: QTranslator | None = None


def _config_option(argv: Sequence[str] | None) -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config")
    options, _rest = parser.parse_known_args(argv)
    return options.config


def install_startup_language(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> str:
    """Choose the language (environment, ``--config``'s ``ui.language``, the system) and install it."""
    language = startup_language(
        _config_option(argv), os.environ if environ is None else environ, QLocale.system().name()
    )
    i18n.install(language)
    return language


def install_qt_translator(app: QCoreApplication, language: str | None = None) -> bool:
    """Qt's own texts (standard buttons, file dialogs) follow the language of the program.

    Replaces the translator of an earlier call. Whether a Qt catalog was found for the language
    (Qt's source language is English, so ``en`` needs none).
    """
    global _qt_translator
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    translator = QTranslator()
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(QLocale(language or i18n.current_language()), "qtbase", "_", path):
        return False
    app.installTranslator(translator)
    _qt_translator = translator
    return True


def restart_notice(setting: str) -> str:
    """What "Recarregar config.yaml" tells when ``ui.language`` now asks for another language
    than the running one, else an empty text."""
    system_name = QLocale.system().name()
    if not changes_on_restart(setting, i18n.current_language(), os.environ, system_name):
        return ""
    return _("O idioma muda ao reiniciar o Lain.")
