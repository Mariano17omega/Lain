"""Which language the program starts in (``ui.language``, spec end R2), without Qt.

It runs before the modules that hold texts are imported (``__main__``), so it reads the
environment, the command line's ``--config`` and the config file's ``ui.language`` key on its own
and never fails: a broken file is reported later, by ``load_config``, in the language chosen here.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import yaml

from ..i18n import LANGUAGES
from .config import ConfigError, find_config

ENV_LANGUAGE = "QE_STUDIO_LANGUAGE"
ENV_LANGUAGE_ALIAS = "LAIN_LANGUAGE"  # the product's name, accepted as well
SETTINGS = ("auto", *LANGUAGES)  # the values of ``ui.language``


def follow_system(system_name: str) -> str:
    """``pt_BR`` for a Portuguese system (``pt``, ``pt_PT``…), ``en`` for any other."""
    return "pt_BR" if system_name.lower().startswith("pt") else "en"


def pinned_language(environ: Mapping[str, str], system_name: str = "") -> str | None:
    """The language an environment variable fixes (tests, screenshots), or None."""
    for name in (ENV_LANGUAGE, ENV_LANGUAGE_ALIAS):
        value = environ.get(name, "").strip()
        if value and value != "auto":
            return value if value in LANGUAGES else follow_system(value)
    return None


def resolve_language(setting: str, system_name: str) -> str:
    """The language of a ``ui.language`` value: ``auto`` follows the system."""
    return setting if setting in LANGUAGES else follow_system(system_name)


def configured_language(path: Path | None) -> str:
    """``ui.language`` of the config file at ``path``; ``auto`` when it is absent or unreadable."""
    if path is None:
        return "auto"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return "auto"
    ui = data.get("ui") if isinstance(data, dict) else None
    value = ui.get("language") if isinstance(ui, dict) else None
    return value if value in SETTINGS else "auto"


def startup_language(
    cli_path: str | os.PathLike[str] | None,
    environ: Mapping[str, str],
    system_name: str,
) -> str:
    """The language to install: the environment first, then ``ui.language``, then the system."""
    pinned = pinned_language(environ, system_name)
    if pinned is not None:
        return pinned
    try:
        path = find_config(cli_path, environ)
    except ConfigError:
        path = None
    return resolve_language(configured_language(path), system_name)


def changes_on_restart(
    setting: str, current: str, environ: Mapping[str, str], system_name: str
) -> bool:
    """Whether the config's ``ui.language`` would start the program in another language than the
    running one. An environment variable fixes the language, so the config does not matter then."""
    if pinned_language(environ, system_name) is not None:
        return False
    return resolve_language(setting, system_name) != current
