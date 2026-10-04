"""What the text viewer shows of a file (spec 10 R4, spec 11 R4, spec 4 R4): the text or its ends,
the banner, the real line numbers, and for a QE input its write checks and key parameters.

Read in a worker: a file can be big or on a network disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import textfile
from .file_kinds import human_size, is_job_log
from .qe.input_extract import Chip, extract
from .qe.input_lint import InputDoc, lint
from .sniff import INPUT_READ_LIMIT, FileSniff, looks_like_input, sniff
from .textfile import LineMap


@dataclass(frozen=True)
class TextPreview:
    text: str
    banner: str
    level: str  # warning / success / error: the banner's color
    line_map: LineMap
    size: int
    highlight: bool  # QE output or job log: color it
    is_input: bool = False  # a QE input: color it as one
    input_doc: InputDoc | None = None  # its lint; None when too big to check (spec 11 R4.2)
    chips: tuple[Chip, ...] = ()  # its extract

    @property
    def truncated(self) -> bool:
        return self.line_map.truncated

    @property
    def omitted_lines(self) -> int:
        """Lines left out between head and tail (0 when the text is whole)."""
        start = self.line_map.marker_start
        return 0 if start is None else self.line_map.tail_first_line - 1 - start


def _sniff(path: Path) -> FileSniff | None:
    try:
        return sniff(path)
    except OSError:
        return None


def read_preview(path: Path, full: bool = False) -> TextPreview:
    """Text, banner and line numbers of ``path``. Queue logs say whether the job wrote errors
    (spec 4 R4); a large file is cut to its ends unless ``full`` (spec 10 R4)."""
    piece = textfile.read_slice(path, full=full)
    banner, level = "", "warning"
    if piece.truncated:
        banner = (
            f"Arquivo grande ({human_size(piece.size)}): exibindo o primeiro "
            f"{human_size(textfile.HEAD_BYTES)} e os últimos {human_size(textfile.TAIL_BYTES)}."
        )
    elif full and piece.size > textfile.LARGE_FILE:
        banner = f"Arquivo completo ({human_size(piece.size)})."
    job_log = is_job_log(path)
    info = _sniff(path)
    output = info is not None and info.is_output
    # A redirected QE output is judged by the run itself, as in the file label.
    judged_by_run = output and info is not None and info.job_done is not None
    if job_log and not judged_by_run:
        if piece.text:
            job, level = "O job registrou mensagens de erro.", "error"
        else:
            job, level = "Arquivo vazio: o job não registrou erros.", "success"
        banner = f"{job} {banner}".rstrip()
    is_input = not (job_log or output) and looks_like_input(path)
    doc = None
    if is_input:
        if piece.size <= INPUT_READ_LIMIT:  # below the viewer's own limit: the text is whole
            doc = lint(piece.text)
        else:
            note = f"Input grande ({human_size(piece.size)}): a escrita não foi verificada, só o realce."
            banner = f"{note} {banner}".rstrip()
    chips = extract(doc) if doc is not None else ()
    return TextPreview(
        piece.text,
        banner,
        level,
        piece.line_map,
        piece.size,
        job_log or output,
        is_input,
        doc,
        chips,
    )
