"""The translation catalogs of the program (spec end R1.4).

The texts in the code are Portuguese (the source language); English lives in
``src/qe_studio/locale/en/LC_MESSAGES/lain.po``. The workflow after changing a text:

    uv run python scripts/i18n.py update    # new and changed messages go into the .po, empty
    # ... translate the empty (and review the "fuzzy") entries in lain.po ...
    uv run python scripts/i18n.py compile   # lain.po → lain.mo (versioned); refuses unfinished work

    uv run python scripts/i18n.py extract   # only src → locale/lain.pot (not versioned)
    uv run python scripts/i18n.py check     # what ``update`` would still leave to do

The ``.po`` and the compiled ``.mo`` are both versioned, so ``uv run lain`` needs no build step.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from babel.messages.catalog import Catalog
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


def po_path(language: str) -> Path:
    return LOCALE / language / "LC_MESSAGES" / f"{DOMAIN}.po"


def mo_path(language: str) -> Path:
    return po_path(language).with_suffix(".mo")


def new_catalog(language: str | None = None) -> Catalog:
    return Catalog(
        locale=language,
        domain=DOMAIN,
        project="Lain: QE Studio",
        charset="utf-8",
        fuzzy=False,  # the header is not "fuzzy"
    )


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
    return catalog


def problems(catalog: Catalog) -> list[str]:
    """What keeps a catalog from being compiled: untranslated and fuzzy messages."""
    found = []
    for message in catalog:
        if not message.id:  # the header
            continue
        shown = message.id[0] if isinstance(message.id, tuple) else message.id
        if message.fuzzy:
            found.append(f"fuzzy: {shown!r}")
        strings = message.string if isinstance(message.string, tuple) else (message.string,)
        if any(not text for text in strings):
            found.append(f"untranslated: {shown!r}")
    return found


def compile_catalog(language: str) -> list[str]:
    """Write the ``.mo`` of ``language``; the problems found (nothing written) if it is unfinished."""
    catalog = read_catalog(po_path(language), language)
    found = problems(catalog)
    if found:
        return found
    with mo_path(language).open("wb") as handle:
        write_mo(handle, catalog, use_fuzzy=False)
    return []


def print_problems(todo: list[str]) -> None:
    for line in todo[:50]:
        print("  ", line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["extract", "update", "compile", "check"])
    args = parser.parse_args(argv)
    status = 0
    if args.command == "compile":  # the .po alone: no need to scan the sources
        for language in LANGUAGES:
            todo = compile_catalog(language)
            if todo:
                print(f"{language}: not compiled, {len(todo)} problems")
                print_problems(todo)
                status = 1
            else:
                print(f"{language}: {mo_path(language).relative_to(ROOT)}")
        return status
    template = extract()
    if args.command == "extract":
        write_catalog(POT, template)
        print(f"{len(template)} messages → {POT.relative_to(ROOT)}")
        return 0
    for language in LANGUAGES:
        if args.command == "update":
            catalog = update(template, language)
            write_catalog(po_path(language), catalog)
            todo = problems(catalog)
            print(f"{language}: {len(catalog)} messages, {len(todo)} to translate or review")
        else:
            todo = problems(update(template, language))
            print(f"{language}: {len(todo)} to translate or review")
            print_problems(todo)
            status = status or int(bool(todo))
    return status


if __name__ == "__main__":
    sys.exit(main())
