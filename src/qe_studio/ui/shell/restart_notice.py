"""What "Recarregar config.yaml" does beyond the window: it applies the log settings at once
(``log:``, spec 89 R4), puts the new config in the log (spec 90 R2.4) and tells about the settings
that apply only after a restart: the language (``ui.language``) and the data folder (``paths.data``,
spec 61 R2.7)."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QSettings

from ...core.app import logs
from ...core.appdirs import data_dir_differs, settings_file
from ...core.config import AppConfig, LoadedConfig
from ...i18n import _
from .language_install import restart_notice

log = logging.getLogger(__name__)


def restart_notices(config: AppConfig) -> str:
    """The notices of ``config`` that need a restart, joined; an empty text when there is none."""
    notices = [restart_notice(config.ui.language)]
    if data_dir_differs(config.paths.data):
        notices.append(_("A pasta de dados muda ao reiniciar o Lain."))
    return " ".join(notice for notice in notices if notice)


def reload_notices(loaded: LoadedConfig) -> str:
    """Apply the log settings of ``loaded``, then log the config under them; what to tell about
    them and about a restart, joined."""
    notices = [logs.apply_config(loaded.config.log), restart_notices(loaded.config)]
    log.info("session: config reloaded from %s", loaded.path)
    # The file of ``ui/app.py:open_settings``, which the window that calls this does not pass on.
    settings = str(settings_file() or QSettings().fileName())
    for line in logs.session_lines(loaded, settings):
        log.info("%s", line)
    for warning in loaded.warnings:
        log.warning("session: %s", warning)
    return " ".join(notice for notice in notices if notice)
