"""Which input belongs to a pw.x output: the one with the same name (``X.out`` → ``X.in``).

Shared by "Gerar SCF convergido" (``scf_from_relax.pair_input``) and the relax module's
``finalize`` (spec 35 R2), so both read a folder with several runs the same way.
"""

from __future__ import annotations

from pathlib import Path

from ..sniff import looks_like_input


def same_name_input(output: Path) -> Path | None:
    """``output`` with the suffix ``.in``, when that file exists and is a QE input (head only)."""
    same = output.with_suffix(".in")
    if same != output and same.is_file() and looks_like_input(same):
        return same
    return None
