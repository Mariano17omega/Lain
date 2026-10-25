"""Names of the exported files (spec 32 R3): the path from the project root, then the plot's own name.

``<local_root>/projeto_ilita/bulk/bandas`` exports ``projeto_ilita-bulk-bandas-bands.png``. Pure: no
disk is read and nothing is resolved (like ``core.projects.project_of``).
"""

from __future__ import annotations

from pathlib import Path

from ..scratch import SCRATCH_PLOTS_DIR, is_scratch

SEPARATOR = "-"
# The exports folder of a simulation. Here, not in export.py: no matplotlib for who only needs the name.
PLOTS_DIR = "plots"
# Room left in the file system's 255 bytes for ``_NN``, the longest extension and the ``.….tmp`` of
# the atomic write.
MAX_STEM_BYTES = 180


def plots_folder(folder: Path) -> Path:
    """Where the figures, CSVs and ``.plot`` files of ``folder`` go: ``folder/plots``, or
    ``folder/plots_remote`` when ``folder`` is the scratch copy of a remote plot (spec 66 R1.2)."""
    return Path(folder) / (SCRATCH_PLOTS_DIR if is_scratch(folder) else PLOTS_DIR)


def export_prefix(folder: Path, root: Path) -> str:
    """The folders from ``root`` down to ``folder`` joined by ``-``. ``folder`` is the root itself:
    nothing (the name stays the plot's, as before). Outside the root: the folder's own name."""
    try:
        parts = Path(folder).relative_to(root).parts
    except ValueError:
        parts = (Path(folder).name,) if Path(folder).name else ()
    return SEPARATOR.join(parts)


def join_stem(prefix: str, suffix: str) -> str:
    """``prefix-suffix`` (just ``suffix`` without a prefix), at most ``MAX_STEM_BYTES`` of UTF-8.

    Too long: whole parts of the prefix go, from the left, so the simulation's own folder and the
    suffix stay; a single part still too long is cut at its end. No leading dot (it would be a
    hidden file, and the temporary of an export is named with one) and no leading ``-``.
    """
    parts = [part for part in prefix.split(SEPARATOR) if part]
    while parts and _size(parts, suffix) > MAX_STEM_BYTES:
        if len(parts) == 1:
            parts[0] = _cut(parts[0], MAX_STEM_BYTES - len(suffix.encode()) - len(SEPARATOR))
            break
        del parts[0]
    stem = SEPARATOR.join([*parts, suffix]) if parts and parts[0] else suffix
    return stem.lstrip(".-") or suffix


def _size(parts: list[str], suffix: str) -> int:
    return len(SEPARATOR.join([*parts, suffix]).encode())


def _cut(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` bytes of UTF-8, on a character boundary."""
    return text.encode()[: max(limit, 0)].decode(errors="ignore")
