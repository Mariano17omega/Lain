"""The translation catalogs of the program (spec end R1.4, spec 52 R1).

The texts in the code are Portuguese (the source language); English lives in
``src/qe_studio/locale/en/LC_MESSAGES/lain.po``. The workflow after changing a text:

    uv run python scripts/i18n.py update    # new and changed messages go into the .po, empty
    # ... translate the empty (and review the "fuzzy") entries in lain.po ...
    uv run python scripts/i18n.py compile   # lain.po → lain.mo (versioned): the translated messages

    uv run python scripts/i18n.py check            # untranslated messages per area, and the problems
    uv run python scripts/i18n.py check --area 53  # the untranslated messages of one area (a spec)
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
import importlib.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

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
AREAS_FILE = ROOT / "tests" / "i18n_areas.py"
WIDTH = 100

# What a translation keeps from its source (spec 52 R3): the ``str.format`` fields, the rich-text
# tags and the ``&`` (namelists, Qt mnemonics). Only real tag names: ``<pasta>/<nome>.xsf`` and
# ``<filband>`` are words of a message, translated with it.
FIELD = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(?:![rsa])?(?::[^{}]*)?\}")
TAG = re.compile(
    r"</?(?:a|b|i|u|s|p|br|hr|em|strong|code|tt|pre|span|div|small|big|sub|sup|ul|ol|li|table"
    r"|tr|td|th|img|font|nobr|qt|html|body|h[1-6])\b[^<>]*>",
    re.IGNORECASE,
)


class Area(NamedTuple):
    """The messages of an area: how many, and the untranslated ones with their files there."""

    total: int
    pending: list[tuple[Message, list[str]]]


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


def load_areas() -> ModuleType:
    """``tests/i18n_areas.py``: which spec translates which file (spec 52 R2, until spec 60)."""
    spec = importlib.util.spec_from_file_location("i18n_areas", AREAS_FILE)
    if spec is None or spec.loader is None:
        raise ImportError(AREAS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def area_numbers(areas: ModuleType) -> list[int]:
    return sorted({areas.DEFAULT_AREA, *areas.AREAS.values()})


def by_area(catalog: Catalog, area_of: Callable[[str], int]) -> dict[int, Area]:
    """Per area (the number of the spec that translates it): its messages, a message counting in
    every area it has a location in, and the untranslated ones with their files in that area."""
    totals: dict[int, int] = {}
    pending: dict[int, list[tuple[Message, list[str]]]] = {}
    for message in messages(catalog):
        files: dict[int, set[str]] = {}
        for filename, _line in message.locations:
            files.setdefault(area_of(filename), set()).add(filename)
        for area, names in files.items():
            totals[area] = totals.get(area, 0) + 1
            if is_pending(message):
                pending.setdefault(area, []).append((message, sorted(names)))
    return {area: Area(total, pending.get(area, [])) for area, total in sorted(totals.items())}


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


def check(language: str, catalog: Catalog, area: int | None) -> int:
    """The table of the areas, or the work list of one; 1 while anything is left to do there."""
    areas = load_areas()
    numbers = area_numbers(areas)
    table = by_area(catalog, areas.area_of)
    found = problems(catalog)
    if area is not None:
        if area not in numbers:
            print(f"no area {area}; the areas are {', '.join(map(str, numbers))}", file=sys.stderr)
            return 2
        pending = table[area].pending if area in table else []
        print(f"{language}, area {area}: {len(pending)} untranslated")
        by_file = sorted(pending, key=lambda item: item[1])
        print_lines([f"{sources(m)[0]!r} ({', '.join(files)})" for m, files in by_file], None)
        print_lines(found)
        return int(bool(pending or found))
    print(f"{language}: {summary(catalog)}")
    print(f"   {'area':>4}  {'total':>5}  untranslated")
    for number in numbers:
        entry = table.get(number, Area(0, []))
        print(f"   {number:>4}  {entry.total:>5}  {len(entry.pending):>12}")
    print_lines(found)
    return int(bool(found) or any(is_pending(message) for message in messages(catalog)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["extract", "update", "compile", "check"])
    parser.add_argument("--area", type=int, help="check: the untranslated messages of one area")
    args = parser.parse_args(argv)
    if args.area is not None and args.command != "check":
        parser.error("--area goes with check")
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
            status = max(status, check(language, catalog, args.area))
    return status


if __name__ == "__main__":
    sys.exit(main())
