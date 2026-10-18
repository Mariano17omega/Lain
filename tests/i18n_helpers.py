"""Helpers of the i18n tests (spec 52): the catalog script, the leak probe and the per-area gate."""

from __future__ import annotations

import functools
import importlib.util
import json
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
    language: str, *scenarios: str, project: Path | None = None
) -> dict[str, list[str]]:
    """``{scenario: texts}`` of the window in ``language``, from ``tests/i18n_probe.py``."""
    command = [sys.executable, str(PROBE), "--language", language]
    if project is not None:
        command += ["--project", str(project)]
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


def leaks(texts: Iterable[str], catalog) -> list[str]:
    """The texts shown in Portuguese although the catalog translates them: equal to a msgid (either
    plural form) whose translation is not empty and differs from it."""
    tool = script()
    translated = set()
    for message in tool.messages(catalog):
        for source, string in zip(tool.sources(message), tool.forms(message), strict=False):
            if string and string != source:
                translated.add(without_mnemonics(source))
    return sorted({text for text in texts if without_mnemonics(text) in translated})


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
