"""Text of a file for the viewer (spec 10): whole, or head + tail when it is large.

QE logs matter at both ends, so a large file shows its beginning and its end with a marker in the
middle. The viewer still wants real line numbers after the marker, so the omitted range is read
once, in streaming, to count its line breaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...i18n import _
from .. import cancel

LARGE_FILE = 4 * 1024 * 1024
HEAD_BYTES = 1024 * 1024
TAIL_BYTES = 2 * 1024 * 1024
LOAD_ALL_LIMIT = 64 * 1024 * 1024  # "Carregar tudo" refuses larger files
MARKER = _("\n\n    [ … trecho omitido pelo visualizador … ]\n\n")
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


def _line_breaks(data: bytes, after_cr: bool = False) -> int:
    """The line breaks the text editor sees in ``data``: ``\\n``, ``\\r``, and ``\\r\\n`` as one.
    ``after_cr``: the byte before ``data`` was a ``\\r``, which a ``\\n`` at its start belongs to."""
    breaks = data.count(b"\n") + data.count(b"\r") - data.count(b"\r\n")
    return breaks - 1 if after_cr and data.startswith(b"\n") else breaks


def _count_breaks(handle, start: int, end: int, after_cr: bool) -> tuple[int, bool]:
    """The line breaks of the bytes ``[start, end)``, and whether what was read ends in ``\\r``."""
    handle.seek(start)
    remaining, count = max(0, end - start), 0
    while remaining > 0:
        cancel.check()
        chunk = handle.read(min(_CHUNK, remaining))
        if not chunk:
            break
        count += _line_breaks(chunk, after_cr)
        after_cr = chunk.endswith(b"\r")
        remaining -= len(chunk)
    return count, after_cr


def _read_whole(handle, size: int) -> str:
    """The whole file, in chunks (the task can be cancelled between them) into one buffer."""
    buffer = bytearray(size)
    view, filled = memoryview(buffer), 0
    while filled < size:
        cancel.check()
        got = handle.readinto(view[filled : filled + _CHUNK])
        if not got:  # the file shrank meanwhile
            break
        filled += got
    view.release()
    del buffer[filled:]
    return buffer.decode("utf-8", "replace")


def read_slice(path: Path, full: bool = False) -> TextSlice:
    """The file's text; above ``LARGE_FILE`` (unless ``full``) its head and tail with a marker.

    A line is what the editor shows as one, so the numbers are those of the whole file: ``\\n``, a
    lone ``\\r`` and ``\\r\\n`` end it. A U+2029, which no run log holds, is not counted.
    """
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if full or size <= LARGE_FILE:
            return TextSlice(_read_whole(handle, size), size)
        head = handle.read(HEAD_BYTES)
        tail_start = size - TAIL_BYTES
        omitted, after_cr = _count_breaks(handle, HEAD_BYTES, tail_start, head.endswith(b"\r"))
        handle.seek(tail_start)
        tail = handle.read()
    # A \r\n cut by the start of the tail was counted at its \r; its \n opens one more block.
    crlf_cut = after_cr and tail.startswith(b"\n")
    line_map = LineMap(
        tail_block=_line_breaks(head + MARKER.encode("utf-8")),
        tail_first_line=_line_breaks(head) + omitted + 1 - crlf_cut,
    )
    text = head.decode("utf-8", "replace") + MARKER + tail.decode("utf-8", "replace")
    return TextSlice(text, size, line_map)
