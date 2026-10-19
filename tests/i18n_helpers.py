"""Helpers of the i18n tests (spec 52): the catalog script, the leak probe and the per-area gate."""

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

from i18n_areas import area_of

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


# The pieces of code inside a sentence that a translation must keep as written (spec 54 R1.3). A
# command-line option is not preceded by a word character or a hyphen: the "-pontos" of "k-pontos"
# and the "-relax" of "vc-relax" are words.
CODE_TOKENS = (
    re.compile(r"`[^`]+`"),
    re.compile(r"&[A-Z_]+"),  # a namelist
    re.compile(r"(?<![\w-])-[A-Za-z]+\b"),  # an option: -pe, -N
    re.compile(r"\bJOB DONE\b"),
    re.compile(r"#!"),
    re.compile(r"\b[A-Z]+_[A-Z_]+\b"),  # a card or a variable: CELL_PARAMETERS
    re.compile(r"\b[a-z]+\(\d\)"),  # celldm(1)
    re.compile(r"\\+[A-Za-z]"),  # an escape shown as text: \r
)


def lost_code_tokens(catalog, done: set[int]) -> list[str]:
    """What a translation of an area of ``done`` dropped or changed of its source's code pieces
    (``CODE_TOKENS``), as ``'<text>': lost <token>``; each plural form against its own source."""
    tool = script()
    found = []
    for message in tool.messages(catalog):
        if not any(area_of(filename) in done for filename, _line in message.locations):
            continue
        for source, string in zip(tool.sources(message), tool.forms(message), strict=False):
            if not string:
                continue
            for pattern in CODE_TOKENS:
                for token in sorted(set(pattern.findall(source)) - set(pattern.findall(string))):
                    found.append(f"{source!r}: lost {token!r}")
    return found


def untranslated_in_done(catalog, done: set[int]) -> list[str]:
    """What the per-area gate (spec 52 R2) refuses: a fuzzy message, and an untranslated one with a
    location in an area of ``done``, as ``area N: '<text>' (<file>)``."""
    tool = script()
    found = []
    for message in tool.messages(catalog):
        text = tool.sources(message)[0]
        if message.fuzzy:
            found.append(f"fuzzy: {text!r}")
        if not tool.is_pending(message):
            continue
        for filename, _line in message.locations:
            if area_of(filename) in done:
                found.append(f"area {area_of(filename)}: {text!r} ({filename})")
    return found


def first_lines(lines: list[str], limit: int = 20) -> str:
    """At most ``limit`` lines of a failure message, and how many there are."""
    more = f"\n… {len(lines)} in all" if len(lines) > limit else ""
    return "\n".join(lines[:limit]) + more
