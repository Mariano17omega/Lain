"""What "Recarregar config.yaml" tells about the settings that apply only after a restart: the
language (``ui.language``) and the data folder (``paths.data``, spec 61 R2.7)."""

from __future__ import annotations

from ..core.appdirs import data_dir_differs
from ..core.config import AppConfig
from ..i18n import _
from .language import restart_notice


def restart_notices(config: AppConfig) -> str:
    """The notices of ``config`` that need a restart, joined; an empty text when there is none."""
    notices = [restart_notice(config.ui.language)]
    if data_dir_differs(config.paths.data):
        notices.append(_("A pasta de dados muda ao reiniciar o Lain."))
    return " ".join(notice for notice in notices if notice)
