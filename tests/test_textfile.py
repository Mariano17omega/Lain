"""core/textfile.py: whole or head+tail text of a file, with real line numbers (spec 10 R3.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qe_studio.core import textfile
from qe_studio.core.textfile import LineMap, read_slice


@pytest.fixture
def small_limits(monkeypatch):
    """A 'large file' of a few hundred bytes: head 100 B, tail 200 B, truncation above 400 B."""
    monkeypatch.setattr(textfile, "LARGE_FILE", 400)
    monkeypatch.setattr(textfile, "HEAD_BYTES", 100)
    monkeypatch.setattr(textfile, "TAIL_BYTES", 200)


def numbered_file(path: Path, lines: int) -> list[str]:
    """``lines`` fixed-width lines ("L00001"), returned without their newline."""
    rows = [f"L{i:05d}" for i in range(1, lines + 1)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return rows


def test_small_file_is_whole(tmp_path):
    path = tmp_path / "a.out"
    path.write_text("one\ntwo\n")
    piece = read_slice(path)
    assert piece.text == "one\ntwo\n" and not piece.truncated
    assert piece.line_map.number(0) == 1 and piece.line_map.block(2) == 1


def test_large_file_keeps_both_ends(small_limits, tmp_path):
    path = tmp_path / "big.out"
    rows = numbered_file(path, 120)
    piece = read_slice(path)
    assert piece.truncated and piece.size == path.stat().st_size
    assert piece.text.startswith(rows[0]) and piece.text.rstrip().endswith(rows[-1])
    assert "trecho omitido" in piece.text


def test_numbers_after_the_marker_are_the_real_ones(small_limits, tmp_path):
    path = tmp_path / "big.out"
    rows = numbered_file(path, 120)
    piece = read_slice(path)
    blocks = piece.text.split("\n")
    line_map = piece.line_map
    marker = next(i for i, text in enumerate(blocks) if "trecho omitido" in text)
    assert line_map.marker_start is not None and line_map.marker_start <= marker
    assert [line_map.number(b) for b in range(line_map.marker_start, line_map.tail_block or 0)] == [
        None,
        None,
        None,
    ]
    # Every block of the tail but its first (cut mid-line) shows the real line it came from.
    for block in range((line_map.tail_block or 0) + 1, len(blocks)):
        text = blocks[block]
        if text:
            assert text == rows[(line_map.number(block) or 0) - 1]
    # The first tail line is a piece of the real line it carries.
    first = blocks[line_map.tail_block or 0]
    assert first and first in rows[(line_map.number(line_map.tail_block or 0) or 0) - 1]
    # Head lines are numbered from 1.
    assert blocks[0] == rows[0] and line_map.number(0) == 1


def test_omitted_newlines_are_counted_in_streaming(small_limits, monkeypatch, tmp_path):
    monkeypatch.setattr(textfile, "_CHUNK", 7)  # many chunks, none aligned with the lines
    path = tmp_path / "big.out"
    data = b"x\n" * 300
    path.write_bytes(data)
    piece = read_slice(path)
    head_lines = data[: textfile.HEAD_BYTES].count(b"\n")
    omitted = data[textfile.HEAD_BYTES : len(data) - textfile.TAIL_BYTES].count(b"\n")
    assert piece.line_map.tail_first_line == head_lines + omitted + 1


def test_full_reads_everything(small_limits, tmp_path):
    path = tmp_path / "big.out"
    numbered_file(path, 120)
    piece = read_slice(path, full=True)
    assert not piece.truncated and piece.text == path.read_text(encoding="utf-8")
    assert "trecho omitido" not in piece.text


def test_line_map_round_trip(small_limits, tmp_path):
    path = tmp_path / "big.out"
    numbered_file(path, 120)
    line_map = read_slice(path).line_map
    assert line_map.truncated
    for number in (1, 2, line_map.marker_start or 0):
        assert line_map.number(line_map.block(number) or 0) == number
    omitted = (line_map.marker_start or 0) + 1
    if omitted < line_map.tail_first_line:
        assert line_map.block(omitted) is None
    last = line_map.tail_first_line + 3
    assert line_map.number(line_map.block(last) or 0) == last
    assert line_map.block(0) is None and LineMap().block(0) is None
    assert LineMap().number(4) == 5 and LineMap().block(5) == 4
