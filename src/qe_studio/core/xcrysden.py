"""Open a pw.x input or output with XCrySDen (spec 45).

Qt-free. ``option_for`` says which XCrySDen option reads a file kind, ``locate`` turns the configured
``paths.xcrysden_path`` (the install folder or the ``xcrysden`` script) into an executable or the
reason there is none, and ``command`` builds the argv. The menu item that uses them lives in
``ui/widgets/context_menu.py``; nothing here starts a process.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

from .sniff import FileKind

EXECUTABLE = "xcrysden"  # the launcher script at the top of an XCrySDen install
# XCrySDen 1.6.2 (`xcrysden --help`): --pwi reads a pw.x input, --pwo a pw.x output.
OPTIONS: dict[FileKind, str] = {FileKind.PW_IN: "--pwi", FileKind.PW_OUT: "--pwo"}

NOT_SET = "Defina paths.xcrysden_path no config.yaml para abrir com o XCrysDen."


class Located(NamedTuple):
    executable: Path | None  # None: it cannot run, ``problem`` says why
    problem: str  # "" when ``executable`` is set


def option_for(kind: FileKind) -> str | None:
    """The XCrySDen option that opens a file of ``kind``, or None when it cannot (by content: the
    sniff decides what a file is, never its suffix)."""
    return OPTIONS.get(kind)


def locate(configured: str | None) -> Located:
    """The executable behind ``paths.xcrysden_path``, or why there is none. Never raises."""
    if configured is None or not configured.strip():
        return Located(None, NOT_SET)
    target = Path(configured)
    not_found = Located(None, f"XCrysDen não encontrado: {target}.")
    try:
        if target.is_dir():
            candidate = target / EXECUTABLE
            if not candidate.is_file():
                return Located(None, f"Não há o executável {EXECUTABLE} em {target}.")
        elif target.is_file():
            candidate = target
        else:
            return not_found
        if not os.access(candidate, os.X_OK):
            return Located(None, f"{candidate} não é executável.")
    except OSError:
        return not_found
    return Located(candidate, "")


def command(executable: Path, option: str, path: Path) -> list[str]:
    """The argv that opens ``path`` with ``option``. No shell, so a name with spaces stays one
    argument; the path is made absolute because the process runs in the file's folder and a
    relative argument would be resolved there a second time."""
    return [str(executable), option, os.path.abspath(path)]
