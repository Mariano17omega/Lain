"""Text of a file for the viewer (spec 10): whole, or head + tail when it is large.

QE logs matter at both ends, so a large file shows its beginning and its end with a marker in the
middle. The viewer still wants real line numbers after the marker, so the omitted range is read
once, in streaming, to count its line breaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LARGE_FILE = 4 * 1024 * 1024
HEAD_BYTES = 1024 * 1024
TAIL_BYTES = 2 * 1024 * 1024
LOAD_ALL_LIMIT = 64 * 1024 * 1024  # "Carregar tudo" refuses larger files
MARKER = "\n\n    [ … trecho omitido pelo visualizador … ]\n\n"
# Text blocks the marker adds between the last head line and the first tail line: a blank
# one, the marker itself, another blank one.
MARKER_BLOCKS = 3
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class LineMap:
    """Between text block (0-based, as the editor counts) and real line of the file (1-based).

    Whole file: line = block + 1. Truncated file: the blocks of the marker have no line, and the
    ones from ``tail_block`` on continue at ``tail_first_line``.
    """

    tail_block: int | None = None  # first block of the tail; None when the file is whole
    tail_first_line: int = 1  # real line shown in that block
    marker_blocks: int = MARKER_BLOCKS

    @property
    def truncated(self) -> bool:
        return self.tail_block is not None

    @property
    def marker_start(self) -> int | None:
        return None if self.tail_block is None else self.tail_block - self.marker_blocks

    def number(self, block: int) -> int | None:
        """Real line shown by ``block``; None for the marker."""
        if self.tail_block is None or self.marker_start is None or block < self.marker_start:
            return block + 1
        if block < self.tail_block:
            return None
        return self.tail_first_line + block - self.tail_block

    def block(self, number: int) -> int | None:
        """Block that shows real line ``number``; None when out of the file or omitted."""
        if number < 1:
            return None
        if self.tail_block is None or self.marker_start is None:
            return number - 1
        if number <= self.marker_start:
            return number - 1
        if number < self.tail_first_line:
            return None
        return self.tail_block + number - self.tail_first_line


@dataclass(frozen=True)
class TextSlice:
    text: str
    size: int
    line_map: LineMap = LineMap()

    @property
    def truncated(self) -> bool:
        return self.line_map.truncated


def _count_newlines(handle, start: int, end: int) -> int:
    handle.seek(start)
    remaining, count = max(0, end - start), 0
    while remaining > 0:
        chunk = handle.read(min(_CHUNK, remaining))
        if not chunk:
            break
        count += chunk.count(b"\n")
        remaining -= len(chunk)
    return count


def read_slice(path: Path, full: bool = False) -> TextSlice:
    """The file's text; above ``LARGE_FILE`` (unless ``full``) its head and tail with a marker.

    A lone ``\\r`` is not a line break here, so such a file may number its tail a few lines off.
    """
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if full or size <= LARGE_FILE:
            return TextSlice(handle.read().decode("utf-8", "replace"), size)
        head = handle.read(HEAD_BYTES).decode("utf-8", "replace")
        tail_start = size - TAIL_BYTES
        omitted = _count_newlines(handle, HEAD_BYTES, tail_start)
        handle.seek(tail_start)
        tail = handle.read().decode("utf-8", "replace")
    head_lines = head.count("\n")
    line_map = LineMap(
        tail_block=head_lines + MARKER_BLOCKS + 1,
        tail_first_line=head_lines + omitted + 1,
    )
    return TextSlice(head + MARKER + tail, size, line_map)
