"""Content-based identification of Quantum ESPRESSO files.

File names are unreliable (``bands.in`` is a pw.x input in some runs and a bands.x input in
others), so every file is classified by what it contains. Results are cached per
(path, mtime, size) and the cache is thread-safe: sniffing runs in worker threads.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .qe import bands_x, projwfc
from .qe.pw_input import parse_input
from .qe.pw_output import PwOutput, parse_pw_output

HEAD_BYTES = 8 * 1024
TAIL_BYTES = 256 * 1024
FULL_READ_LIMIT = 16 * 1024 * 1024
INPUT_READ_LIMIT = 2 * 1024 * 1024
# pw.x outputs above FULL_READ_LIMIT: the facts printed once at the start (k points, electrons…)
# come from the head, which must hold the site list of big systems; the last ones from the tail.
PW_HEAD_BYTES = 256 * 1024
PW_TAIL_BYTES = 1024 * 1024

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".eps", ".ps", ".gif", ".ipynb", ".py", ".sh",
    ".qsub", ".slurm", ".pbs", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".upf",
    ".cif", ".xsf", ".zip", ".gz", ".tar", ".bz2", ".xz", ".rap", ".xmgr", ".html", ".plot",
}  # fmt: skip


class FileKind(StrEnum):
    PW_IN = "pw_in"
    PW_OUT = "pw_out"
    BANDSX_IN = "bandsx_in"
    BANDSX_OUT = "bandsx_out"
    PROJWFC_IN = "projwfc_in"
    PROJWFC_OUT = "projwfc_out"
    DOS_IN = "dos_in"
    DOS_OUT = "dos_out"
    OTHER_OUT = "other_out"
    GNU_DATA = "gnu_data"
    FILBAND = "filband"
    PDOS_ATM = "pdos_atm"
    PDOS_TOT = "pdos_tot"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FileSniff:
    path: Path
    kind: FileKind
    calculation: str | None = None
    program: str | None = None
    pw: PwOutput | None = field(default=None, repr=False)
    bandsx: bands_x.BandsXOutput | None = field(default=None, repr=False)
    shape: tuple[int, int] | None = None  # (nbnd, nks) for band data files
    job_done: bool | None = None
    warnings: tuple[str, ...] = ()

    @property
    def is_output(self) -> bool:
        return self.kind in {
            FileKind.PW_OUT,
            FileKind.BANDSX_OUT,
            FileKind.PROJWFC_OUT,
            FileKind.DOS_OUT,
            FileKind.OTHER_OUT,
        }


_PROGRAM = re.compile(r"^\s*Program\s+([A-Z0-9_.]+)\s+v\.", re.M)
_NAMELIST = re.compile(r"^\s*&(\w+)", re.M)
_OUTPUT_KINDS = {
    "PWSCF": FileKind.PW_OUT,
    "BANDS": FileKind.BANDSX_OUT,
    "PROJWFC": FileKind.PROJWFC_OUT,
    "DOS": FileKind.DOS_OUT,
}
_INPUT_KINDS = {
    "pw": FileKind.PW_IN,
    "bands": FileKind.BANDSX_IN,
    "projwfc": FileKind.PROJWFC_IN,
    "dos": FileKind.DOS_IN,
}


def _read_head(path: Path, size: int = HEAD_BYTES) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(size)


def looks_like_input(path: Path) -> bool:
    """Is ``path`` a QE input, judged by its head only (spec 11 R4.1)?

    True when the head has a ``&name`` line, even if ``sniff`` says UNKNOWN because ASE choked on
    it: a broken input is still an input, shown with its errors marked. Never parses the file,
    so it is cheap enough for the GUI thread. bands.x ``filband`` files (``&plot nbnd=…``), QE
    outputs and text-like suffixes that `sniff` skips do not count.
    """
    if projwfc.parse_atm_name(path.name) or projwfc.is_pdos_tot_name(path.name):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    try:
        raw = _read_head(path)
    except OSError:
        return False
    if b"\x00" in raw:
        return False
    head = raw.decode("utf-8", errors="replace")
    if _PROGRAM.search(head[:2048]) or bands_x.read_filband_header(head):
        return False
    return _NAMELIST.search(head) is not None


def _read_head_tail(
    path: Path, file_size: int, limit: int, head: int = HEAD_BYTES, tail: int = TAIL_BYTES
) -> tuple[str, str]:
    """The whole text as both head and tail (the same object) if the file is at most ``limit``
    bytes, else its first ``head`` and last ``tail`` bytes, cut at line ends so that no pattern
    sees part of a line."""
    with open(path, "rb") as handle:
        if file_size <= limit:
            text = handle.read().decode("utf-8", errors="replace")
            return text, text
        start = handle.read(head)
        handle.seek(max(file_size - tail, head))
        end = handle.read()
    start = start[: start.rfind(b"\n") + 1]
    end = end[end.find(b"\n") + 1 :]
    return start.decode("utf-8", errors="replace"), end.decode("utf-8", errors="replace")


def _read_text(path: Path, file_size: int, limit: int) -> str:
    """Whole file if small enough, else head + tail (markers live at both ends)."""
    head, tail = _read_head_tail(path, file_size, limit)
    return head if head is tail else f"{head}\n{tail}"


def _sniff_uncached(path: Path, size: int) -> FileSniff:
    name = path.name
    if projwfc.parse_atm_name(name):
        return _sniff_pdos(path, FileKind.PDOS_ATM)
    if projwfc.is_pdos_tot_name(name):
        return _sniff_pdos(path, FileKind.PDOS_TOT)
    if path.suffix.lower() in SKIP_SUFFIXES or size == 0:
        return FileSniff(path, FileKind.UNKNOWN)

    raw = _read_head(path)
    if b"\x00" in raw:
        return FileSniff(path, FileKind.UNKNOWN)
    head = raw.decode("utf-8", errors="replace")

    program = _PROGRAM.search(head[:2048])
    if program:
        return _sniff_output(path, size, program.group(1))
    if filband := bands_x.read_filband_header(head):
        nbnd, nks = filband
        return FileSniff(path, FileKind.FILBAND, shape=(nbnd, nks))
    if _NAMELIST.search(head):
        return _sniff_input(path, size)
    if path.suffix.lower() == ".gnu":
        try:
            with open(path, "rb") as handle:
                shape = bands_x.gnu_shape(handle)  # streamed: no size limit, ``load`` parses
        except bands_x.BandsFormatError:
            return FileSniff(path, FileKind.UNKNOWN)
        return FileSniff(path, FileKind.GNU_DATA, shape=shape)
    return FileSniff(path, FileKind.UNKNOWN)


def _sniff_pdos(path: Path, kind: FileKind) -> FileSniff:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            projwfc.header_columns(handle.readline())
    except projwfc.PdosFormatError as exc:
        return FileSniff(path, kind, warnings=(str(exc),))
    except OSError:
        return FileSniff(path, FileKind.UNKNOWN)
    return FileSniff(path, kind)


def _sniff_output(path: Path, size: int, program: str) -> FileSniff:
    kind = _OUTPUT_KINDS.get(program, FileKind.OTHER_OUT)
    if kind is FileKind.PW_OUT:
        head, tail = _read_head_tail(path, size, FULL_READ_LIMIT, PW_HEAD_BYTES, PW_TAIL_BYTES)
        pw = parse_pw_output(head, tail)
        return FileSniff(
            path,
            kind,
            calculation=pw.calculation,
            program=program,
            pw=pw,
            job_done=pw.job_done,
            warnings=tuple(pw.warnings),
        )
    text = _read_text(path, size, FULL_READ_LIMIT if kind is FileKind.BANDSX_OUT else 0)
    job_done = "JOB DONE" in text
    warnings = () if job_done else ("execução incompleta (sem JOB DONE)",)
    bandsx = bands_x.parse_bandsx_output(text) if kind is FileKind.BANDSX_OUT else None
    return FileSniff(
        path, kind, program=program, bandsx=bandsx, job_done=job_done, warnings=warnings
    )


def _sniff_input(path: Path, size: int) -> FileSniff:
    if size > INPUT_READ_LIMIT:
        return FileSniff(path, FileKind.UNKNOWN)
    try:
        parsed = parse_input(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # ASE's namelist reader raises assorted errors on non-inputs
        return FileSniff(path, FileKind.UNKNOWN)
    kind = _INPUT_KINDS.get(parsed.program or "", FileKind.UNKNOWN)
    return FileSniff(path, kind, calculation=parsed.calculation, program=parsed.program)


class SniffCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[Path, tuple[int, int, FileSniff]] = {}

    def sniff(self, path: Path) -> FileSniff:
        try:
            stat = path.stat()
        except OSError:
            return FileSniff(path, FileKind.UNKNOWN)
        stamp = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._entries.get(path)
        if cached and cached[:2] == stamp:
            return cached[2]
        try:
            result = _sniff_uncached(path, stat.st_size)
        except OSError:
            result = FileSniff(path, FileKind.UNKNOWN)
        with self._lock:
            self._entries[path] = (*stamp, result)
        return result

    def peek(self, path: Path) -> FileSniff | None:
        """Cached result without touching the disk (for painting)."""
        with self._lock:
            cached = self._entries.get(Path(path))
        return cached[2] if cached else None

    def invalidate(self, prefix: Path) -> None:
        with self._lock:
            for path in [p for p in self._entries if p.is_relative_to(prefix)]:
                del self._entries[path]

    def prune(self) -> None:
        """Drop the entries of files that no longer exist (one ``stat`` each).

        The rest stay: ``sniff`` already checks their (mtime, size) stamp before use.
        """
        with self._lock:
            paths = list(self._entries)
        gone = [path for path in paths if not path.exists()]
        with self._lock:
            for path in gone:
                self._entries.pop(path, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_default_cache = SniffCache()


def sniff(path: str | os.PathLike[str]) -> FileSniff:
    return _default_cache.sniff(Path(path))
