"""What the ``#$`` lines of an SGE job script (``.qsub``) say: their options, the job's name and slots.

A line ends at ``\\n`` only, as for SGE: ``str.splitlines`` would also cut at a ``\\f`` or a
``\\u2028`` and take the text after it for a directive. A ``\\r`` before the ``\\n`` is just a blank.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

_OPTION = re.compile(r"-[A-Za-z_]+$")
_TOKEN = re.compile(r"(?:\"[^\"]*\"|'[^']*'|[^\s\"'])+")


def directive_lines(text: str) -> Iterator[str]:
    """The ``#$`` lines of the script ``text``."""
    return (line for line in text.split("\n") if line.startswith("#$"))


def directive_tokens(line: str) -> list[tuple[int, str]]:
    """The ``(column, token)`` of the ``#$`` line ``line``, up to its comment."""
    tokens = []
    for match in _TOKEN.finditer(line, 2):
        if match.group().startswith("#"):
            break
        tokens.append((match.start(), match.group()))
    return tokens


def is_option(token: str) -> bool:
    """Does ``token`` have the form of a qsub option (``-pe``)? A negative number does not."""
    return _OPTION.match(token) is not None


def job_name(text: str, script: str) -> str:
    """The name SGE gives the job of the script ``text``: the value of the last ``-N`` of its ``#$``
    lines, quotes stripped, else the script's file name ``script``, as ``qsub`` does (spec 71 R3)."""
    name = ""
    for line in directive_lines(text):
        tokens = [token for _column, token in directive_tokens(line)]
        for k, token in enumerate(tokens):
            value = tokens[k + 1] if k + 1 < len(tokens) else ""
            if token == "-N" and not is_option(value):
                name = value.strip("\"'") or name
    return name or script.rsplit("/", 1)[-1]


def pe_slots(text: str) -> int | None:
    """The slots of the last ``-pe`` of the ``#$`` lines of the script ``text`` (``#$ -pe physica
    64`` → 64), quotes stripped; None without a ``-pe`` or with a range (``32-64``), spec 85 R1."""
    slots = None
    for line in directive_lines(text):
        tokens = [token for _column, token in directive_tokens(line)]
        for k, token in enumerate(tokens):
            if token == "-pe":
                value = tokens[k + 2].strip("\"'") if k + 2 < len(tokens) else ""
                slots = int(value) if value.isdecimal() else None
    return slots
