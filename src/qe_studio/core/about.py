"""What "Sobre o Lain" reports: the versions of the stack, as text to paste into a bug report.

Versions come from the installed metadata, so heavy packages (ASE, spec 14) are never imported.
No Qt: the dialog adds the Qt and PyQt versions itself.
"""

from __future__ import annotations

import platform
from importlib import metadata

PACKAGES = (("matplotlib", "matplotlib"), ("numpy", "numpy"), ("ASE", "ase"))


def package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "não instalado"


def package_versions() -> list[tuple[str, str]]:
    """(name, version) of Python and the scientific stack."""
    rows = [("Python", platform.python_version())]
    rows.extend((label, package_version(dist)) for label, dist in PACKAGES)
    return rows


def report_text(rows: list[tuple[str, str]]) -> str:
    """The rows as ``label: value`` lines (the "Copiar informações" payload)."""
    return "\n".join(f"{label}: {value}" for label, value in rows)
