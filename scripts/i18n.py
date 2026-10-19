"""The translation catalogs of the program (spec end R1.4, specs 52 and 60).

The texts in the code are Portuguese (the source language); English lives in
``src/qe_studio/locale/en/LC_MESSAGES/lain.po``. The workflow after changing a text:

    uv run python scripts/i18n.py update    # new and changed messages go into the .po, empty
    # ... translate the empty (and review the "fuzzy") entries in lain.po ...
    uv run python scripts/i18n.py compile   # lain.po → lain.mo (versioned): the translated messages

    uv run python scripts/i18n.py check            # exit 0 only if every message is translated (CI)
    uv run python scripts/i18n.py extract          # only src → locale/lain.pot (not versioned)

A message left empty is shown in Portuguese: the ``.mo`` carries the translated ones only.
``compile`` refuses a "fuzzy" message, a plural with an empty form and a translation that lost or
gained a ``{field}``, a tag or an ``&`` of its source. The ``.po`` and the ``.mo`` are both versioned
and committed together, so ``uv run lain`` needs no build step. More in
``src/qe_studio/locale/README.md``.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from babel.messages.catalog import Catalog, Message
from babel.messages.extract import extract_from_dir
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

from qe_studio import i18n
from qe_studio.i18n import DOMAIN

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "qe_studio"
LOCALE = SOURCE / "locale"
LANGUAGES = tuple(  # the source language, pt_BR, needs no catalog
    language for language in i18n.LANGUAGES if language != i18n.SOURCE_LANGUAGE
)
POT = LOCALE / f"{DOMAIN}.pot"
WIDTH = 100
PROJECT = "Lain: QE Studio"
AUTHOR = "Mariano Sobrinho"  # the project's author: translator, copyright holder and contact
CONTACT = "onairam17@gmail.com"
TEAM = "English"

# What a translation keeps from its source (spec 52 R3): the ``str.format`` fields, the rich-text
# tags and the ``&`` (namelists, Qt mnemonics). Only real tag names: ``<pasta>/<nome>.xsf`` and
# ``<filband>`` are words of a message, translated with it.
FIELD = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(?:![rsa])?(?::[^{}]*)?\}")
TAG = re.compile(
    r"</?(?:a|b|i|u|s|p|br|hr|em|strong|code|tt|pre|span|div|small|big|sub|sup|ul|ol|li|table"
    r"|tr|td|th|img|font|nobr|qt|html|body|h[1-6])\b[^<>]*>",
    re.IGNORECASE,
)


def po_path(language: str) -> Path:
    return LOCALE / language / "LC_MESSAGES" / f"{DOMAIN}.po"


def mo_path(language: str) -> Path:
    return po_path(language).with_suffix(".mo")


def project_version() -> str:
    """The version of ``pyproject.toml``, the one of the header of the catalogs."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def new_catalog(language: str | None = None) -> Catalog:
    return Catalog(
        locale=language,
        domain=DOMAIN,
        project=PROJECT,
        version=project_version(),
        copyright_holder=AUTHOR,
        msgid_bugs_address=CONTACT,
        last_translator=f"{AUTHOR} <{CONTACT}>",
        language_team=TEAM,
        charset="utf-8",
        fuzzy=False,  # the header is not "fuzzy"
    )


def stamp(catalog: Catalog) -> Catalog:
    """The header of a catalog read from a file with no babel placeholder left (spec 60 R4.5): the
    project's version, its translator and contact, the team and the revision date."""
    catalog.project = PROJECT
    catalog.version = project_version()
    catalog.copyright_holder = AUTHOR
    catalog.msgid_bugs_address = CONTACT
    catalog.last_translator = f"{AUTHOR} <{CONTACT}>"
    catalog.language_team = TEAM
    catalog.revision_date = datetime.now().astimezone().replace(microsecond=0)
    year = catalog.revision_date.year
    catalog.header_comment = (
        f"# {TEAM} translations for {PROJECT}.\n"
        f"# Copyright (C) {year} {AUTHOR}\n"
        f"# This file is distributed under the same license as the {PROJECT} project.\n"
        f"# {AUTHOR} <{CONTACT}>, {year}.\n"
        "#"
    )
    return catalog


def extract(source: Path = SOURCE) -> Catalog:
    """The template: every message marked in the code, with where it is (file names only)."""
    catalog = new_catalog()
    found = extract_from_dir(str(source))  # babel's defaults: *.py, and _, N_, ngettext…
    for filename, lineno, message, comments, context in found:
        if not message:
            continue
        catalog.add(
            message, locations=[(filename, lineno)], auto_comments=comments, context=context
        )
    return catalog


def read_catalog(path: Path, language: str) -> Catalog:
    with path.open("rb") as handle:
        return read_po(handle, locale=language, domain=DOMAIN)


def write_catalog(path: Path, catalog: Catalog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        write_po(
            handle,
            catalog,
            width=WIDTH,
            sort_output=True,
            include_lineno=False,
            ignore_obsolete=True,
        )


def update(template: Catalog, language: str) -> Catalog:
    """The catalog of ``language`` after the template: kept translations, new messages empty, the
    ones that left the code dropped, a changed message matched to its old one as "fuzzy"."""
    target = po_path(language)
    catalog = read_catalog(target, language) if target.exists() else new_catalog(language)
    catalog.update(template)
    return stamp(catalog)


def messages(catalog: Catalog) -> list[Message]:
    """The messages of ``catalog``, without its header."""
    return [message for message in catalog if message.id]


def sources(message: Message) -> tuple[str, ...]:
    """The Portuguese of ``message``: ``(msgid,)``, or ``(msgid, msgid_plural)``."""
    return tuple(message.id) if isinstance(message.id, tuple | list) else (message.id,)


def forms(message: Message) -> tuple[str, ...]:
    """The translation of ``message``: one string, or one per plural form."""
    string = message.string
    return tuple(string) if isinstance(string, tuple | list) else (string or "",)


def is_translated(message: Message) -> bool:
    return all(forms(message))


def is_pending(message: Message) -> bool:
    """Untranslated: no form filled, so the program shows the Portuguese."""
    return not any(forms(message))


def markers(text: str) -> tuple[frozenset[str], frozenset[str], int]:
    return frozenset(FIELD.findall(text)), frozenset(TAG.findall(text)), text.count("&")


def problems(catalog: Catalog) -> list[str]:
    """What keeps a catalog from being compiled: a "fuzzy" message, a plural with an empty form and
    a translation whose fields, tags or ``&`` differ from its source (form 0 against the msgid, the
    others against the msgid_plural). An untranslated message is not one: it shows the Portuguese."""
    found = []
    for message in messages(catalog):
        ids, strings = sources(message), forms(message)
        shown = ids[0]
        if message.fuzzy:
            found.append(f"fuzzy: {shown!r}")
        if any(strings) and not all(strings):
            found.append(f"plural with an empty form: {shown!r}")
        for index, string in enumerate(strings):
            if string and markers(string) != markers(ids[min(index, len(ids) - 1)]):
                found.append(f"fields, tags or & differ: {shown!r} → {string!r}")
    return found


def compile_catalog(catalog: Catalog, target: Path) -> list[str]:
    """Write the ``.mo`` of ``catalog`` at ``target`` with its translated messages only; the
    problems found instead, and nothing written. ``catalog`` itself is left as it was."""
    found = problems(catalog)
    if found:
        return found
    compiled = copy.deepcopy(catalog)
    for message in messages(compiled):
        if not is_translated(message):
            compiled.delete(message.id, context=message.context)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        write_mo(handle, compiled, use_fuzzy=False)
    return []


def summary(catalog: Catalog) -> str:
    found = messages(catalog)
    pending = sum(is_pending(message) for message in found)
    return f"{len(found)} messages, {pending} untranslated, {len(problems(catalog))} problems"


def print_lines(lines: list[str], limit: int | None = 50) -> None:
    for line in lines if limit is None else lines[:limit]:
        print("  ", line)
    if limit is not None and len(lines) > limit:
        print(f"   … and {len(lines) - limit} more")


def compile_language(language: str) -> int:
    catalog = read_catalog(po_path(language), language)
    found = compile_catalog(catalog, mo_path(language))
    if found:
        print(f"{language}: not compiled, {len(found)} problems")
        print_lines(found)
        return 1
    total = len(messages(catalog))
    translated = sum(is_translated(message) for message in messages(catalog))
    target = mo_path(language).relative_to(ROOT)
    print(f"{language}: {target} ({translated} translated, {total - translated} in Portuguese)")
    return 0


def check(language: str, catalog: Catalog) -> int:
    """The summary and the problems; 1 while anything is left to do (an untranslated message, a
    fuzzy one or a problem), so CI can run it."""
    found = problems(catalog)
    print(f"{language}: {summary(catalog)}")
    print_lines(found)
    return int(bool(found) or any(is_pending(message) for message in messages(catalog)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["extract", "update", "compile", "check"])
    args = parser.parse_args(argv)
    if args.command == "compile":  # the .po alone: no need to scan the sources
        return max(compile_language(language) for language in LANGUAGES)
    template = extract()
    if args.command == "extract":
        write_catalog(POT, template)
        print(f"{len(template)} messages → {POT.relative_to(ROOT)}")
        return 0
    status = 0
    for language in LANGUAGES:
        catalog = update(template, language)
        if args.command == "update":
            write_catalog(po_path(language), catalog)
            print(f"{language}: {summary(catalog)}")
        else:
            status = max(status, check(language, catalog))
    return status


if __name__ == "__main__":
    sys.exit(main())
