"""A "Baixar" of one file of the cluster (spec 65 R5.2): the pull of its folder, narrowed to it by
rsync filter rules (the controller's ``extra_args``, given to the dry run and to the transfer)."""

from __future__ import annotations

import re

WILDCARDS = frozenset("*?[")
_SPECIAL = re.compile(r"([\[*?\\])")


def only_file_rules(name: str) -> list[str]:
    """The rules that keep only the file ``name`` of the pulled folder: an include anchored at its
    top (``/``: a namesake in a subfolder stays out), then everything else excluded. rsync reads a
    pattern with ``*``, ``?`` or ``[`` as a wildcard one, where ``\\`` escapes the next character;
    any other pattern is compared as it is, backslashes and all, so it is not escaped."""
    pattern = _SPECIAL.sub(r"\\\1", name) if WILDCARDS & set(name) else name
    return [f"--include=/{pattern}", "--exclude=*"]
