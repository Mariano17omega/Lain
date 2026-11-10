"""Translation of the texts the user reads (gettext).

The source language is Portuguese: the strings in the code are the Portuguese messages and the ``pt_BR``
language needs no catalog. English lives in ``locale/en/LC_MESSAGES/lain_<domain>.po``, one catalog (a
gettext domain) per area of the code, compiled to ``.mo`` and versioned. ``install`` chains the domains,
so ``_()`` stays a single function. No Qt here: ``core/`` and ``ui/`` share these functions.

The language is chosen once, at startup, and applies until the program is restarted: ``install`` runs
before the application modules are imported (``__main__`` does it), so a text may be translated
where it is defined, at module level included. ``N_()`` marks a Portuguese message that is also
data (a token compared or stored) and translates nothing: the code that shows it calls ``_()``.
"""

from __future__ import annotations

import gettext
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

DOMAIN = "lain"  # the prefix of every catalog: ``lain_<name>``
# The catalogs, in lookup order: the messages shared by several areas first, then the largest areas.
# ``scripts/i18n.py`` decides which one holds a message (``domain_of``).
DOMAINS = (
    "common",
    "calc_create",
    "calculations",
    "ui",
    "qe",
    "sync",
    "files",
    "structure3d",
    "viewer",
    "core",
)
SOURCE_LANGUAGE = "pt_BR"
LANGUAGES = ("pt_BR", "en")

_translation: gettext.NullTranslations = gettext.NullTranslations()
_language = SOURCE_LANGUAGE


def locale_dir() -> Path:
    return Path(str(files("qe_studio").joinpath("locale")))


def install(language: str) -> None:
    """Load the catalog of ``language``; a language without one shows the source messages.

    Call it before importing the modules that hold texts: a text translated while a module loads
    keeps the language that was installed then.
    """
    global _translation, _language
    _translation = load(language)
    _language = language


def domain_name(domain: str) -> str:
    """The gettext domain, and the file name without extension, of the catalog ``domain``."""
    return f"{DOMAIN}_{domain}"


def load(language: str) -> gettext.NullTranslations:
    """The catalogs of ``language`` chained into one; a domain with no ``.mo`` is skipped."""
    chained = gettext.NullTranslations()
    for domain in DOMAINS:
        try:
            chained.add_fallback(
                gettext.translation(domain_name(domain), str(locale_dir()), languages=[language])
            )
        except OSError:  # no catalog for this language and domain: the source messages show
            continue
    return chained


def current_language() -> str:
    return _language


def _(message: str) -> str:
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


def N_(message: str) -> str:
    """Mark ``message`` for the catalog without translating it (constants built at import)."""
    return message


def join_or(items: Iterable[str]) -> str:
    """``a``, ``a ou b``, ``a, b ou c``: the list the user chooses one of."""
    texts = list(items)
    if len(texts) < 2:
        return "".join(texts)
    return _("{items} ou {last}").format(items=", ".join(texts[:-1]), last=texts[-1])
