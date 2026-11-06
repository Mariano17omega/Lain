"""Helpers of the i18n tests (specs 52, 60): the catalog script, the leak probe and the catalog checks."""

from __future__ import annotations

import functools
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "i18n_probe.py"
PROBE_TIMEOUT_S = 60


@functools.cache
def script() -> ModuleType:
    """``scripts/i18n.py``, loaded by path."""
    spec = importlib.util.spec_from_file_location("i18n_script", ROOT / "scripts" / "i18n.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe_texts(
    language: str, *scenarios: str, project: Path | None = None, plot_dir: Path | None = None
) -> dict[str, list[str]]:
    """``{scenario: texts}`` of the window in ``language``, from ``tests/i18n_probe.py``."""
    command = [sys.executable, str(PROBE), "--language", language]
    if project is not None:
        command += ["--project", str(project)]
    if plot_dir is not None:
        command += ["--plot-dir", str(plot_dir)]
    for scenario in scenarios:
        command += ["--scenario", scenario]
    done = subprocess.run(
        command, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S, cwd=ROOT, check=False
    )
    assert done.returncode == 0, f"the probe failed ({done.returncode}):\n{done.stderr[-3000:]}"
    return json.loads(done.stdout.strip().splitlines()[-1])


def without_mnemonics(text: str) -> str:
    """``text`` as compared: a Qt mnemonic ``&`` dropped, ``&&`` read as ``&``."""
    return "&".join(part.replace("&", "") for part in text.split("&&"))


# Portuguese messages that are also an English text shown elsewhere, so the probe cannot tell the
# translation from a leak. A new one needs its reason here.
HOMOGRAPHS = {
    "Data",  # the file grid's "Data" (date → "Date"); the About row "Dados" is "Data" in English
    "Local",  # the sync table's "Local date" (a computer's side): English "local", not a leak
}


def leaks(texts: Iterable[str], catalog) -> list[str]:
    """The texts shown in Portuguese although the catalog translates them: equal to a msgid (either
    plural form) whose translation is not empty and differs from it."""
    tool = script()
    translated = set()
    for message in tool.messages(catalog):
        for source, string in zip(tool.sources(message), tool.forms(message), strict=False):
            if string and string != source:
                translated.add(without_mnemonics(source))
    translated -= HOMOGRAPHS
    return sorted({text for text in texts if without_mnemonics(text) in translated})


# Variables of QE's inputs that a field of "Criar cálculo" names without a namelist or an underscore
# ("Passos máximos (nstep)"): spec 57 R1.2.
QE_NAMES = (
    *("nstep", "nbnd", "nk", "NP", "degauss", "ngauss", "filpdos", "filband", "fileout", "iflag"),
    *("occupations", "press", "symprec", "DeltaE", "Emin", "Emax"),
)
# The pieces of code inside a sentence that a translation must keep as written (spec 54 R1.3). A
# command-line option is not preceded by a word character or a hyphen: the "-pontos" of "k-pontos"
# and the "-relax" of "vc-relax" are words.
CODE_TOKENS = (
    re.compile(r"`[^`]+`"),
    re.compile(r"&[A-Z_]+"),  # a namelist
    re.compile(r"&[A-Z_]+ [a-z][a-z_]*"),  # a namelist and the variable it names: &CONTROL nstep
    re.compile(r"(?<![\w-])-[A-Za-z]+\b"),  # an option: -pe, -N
    re.compile(r"\bJOB DONE\b"),
    re.compile(r"#!"),
    re.compile(r"\b[A-Z]+_[A-Z_]+\b"),  # a card or a variable: CELL_PARAMETERS
    re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b"),  # a variable: forc_conv_thr, spin_component
    re.compile(r"\b(?:" + "|".join(QE_NAMES) + r")\b"),
    re.compile(r"\b[a-z]+\(\d\)"),  # celldm(1)
    re.compile(r"\\+[A-Za-z]"),  # an escape shown as text: \r
)


def lost_code_tokens(catalog) -> list[str]:
    """What a translation dropped or changed of its source's code pieces
    (``CODE_TOKENS``), as ``'<text>': lost <token>``; each plural form against its own source."""
    tool = script()
    found = []
    for message in tool.messages(catalog):
        for source, string in zip(tool.sources(message), tool.forms(message), strict=False):
            if not string:
                continue
            for pattern in CODE_TOKENS:
                for token in sorted(set(pattern.findall(source)) - set(pattern.findall(string))):
                    found.append(f"{source!r}: lost {token!r}")
    return found


# A Portuguese negation and the words that carry it over in English. A translation of a sentence
# that says what is not done (spec 58 R1.2: "não será alterado") must say it too.
NEGATION_PT = re.compile(r"\b(?:não|nunca|nenhum|nenhuma)\b", re.IGNORECASE)
NEGATION_EN = re.compile(r"\b(?:not|never|no|none|cannot)\b|n't", re.IGNORECASE)


def lost_negations(catalog, under: tuple[str, ...]) -> list[str]:
    """The messages with a location under one of the ``under`` prefixes whose Portuguese says "não"
    (or "nunca"…) and a translation, in some plural form, that says no negation:
    ``'<text>': <form> has no negation``. Scoped, as a "não" that is only part of a name
    ("Aspas não fechadas" → "Unclosed quotes") is no sentence about what is not done."""
    tool = script()
    found = []
    for message in tool.messages(catalog):
        if not any(name.startswith(under) for name, _line in message.locations):
            continue
        for source, string in zip(tool.sources(message), tool.forms(message), strict=False):
            if string and NEGATION_PT.search(source) and not NEGATION_EN.search(string):
                found.append(f"{source!r}: {string!r} has no negation")
    return found


FRAGMENT_WORDS = 4  # longer messages are sentences, not the pieces a composed text takes


def fragment_leaks(texts: Iterable[str], catalog) -> list[str]:
    """Portuguese pieces inside composed texts (spec 57 R2.1): a short translated message
    with no field, found word for word in a text (``regra 'camada inferior'``, the
    token of a choice formatted without ``_()``), as ``'<piece>' in '<text>'``."""
    tool = script()
    pieces = set()
    for message in tool.messages(catalog):
        for source, string in zip(tool.sources(message), tool.forms(message), strict=False):
            if (
                string
                and string != source
                and "{" not in source
                and len(source.split()) <= FRAGMENT_WORDS
                and len(source) >= 4
            ):
                pieces.add(source)
    pieces -= HOMOGRAPHS
    patterns = {piece: re.compile(rf"(?<!\w){re.escape(piece)}(?!\w)") for piece in pieces}
    return sorted(
        f"{piece!r} in {text!r}"
        for text in texts
        for piece, pattern in patterns.items()
        if pattern.search(text)
    )


def pending(catalog) -> list[str]:
    """What keeps the catalog from being complete: a fuzzy message, and an untranslated one with its
    files, as ``'<text>' (<file>, …)``."""
    tool = script()
    found = []
    for message in tool.messages(catalog):
        text = tool.sources(message)[0]
        if message.fuzzy:
            found.append(f"fuzzy: {text!r}")
        if tool.is_pending(message):
            files = sorted({filename for filename, _line in message.locations})
            found.append(f"{text!r} ({', '.join(files)})")
    return found


def first_lines(lines: list[str], limit: int = 20) -> str:
    """At most ``limit`` lines of a failure message, and how many there are."""
    more = f"\n… {len(lines)} in all" if len(lines) > limit else ""
    return "\n".join(lines[:limit]) + more
