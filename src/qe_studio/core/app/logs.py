"""The program's log (spec 89): the only module that configures ``logging``.

It starts in two steps, because the file's folder and limit come from the config: ``start`` (the
first thing ``main`` does) keeps what is logged in memory, and ``apply_config`` (once the config is
read and the data folder fixed, and again on every "Recarregar config.yaml") opens, changes or
closes the file. Only the ``qe_studio`` logger goes below WARNING: the libraries' DEBUG would fill
any limit (matplotlib's font manager alone logs thousands of records for one figure).

What each level holds is spec 90: INFO tells the session, DEBUG adds what repeats, and what would
get lost otherwise comes here too (a Python warning, an exception in a thread). A native crash never
reaches ``logging``: ``faulthandler`` writes it to ``lain.crash``, and the next session logs it.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import platform
import threading
from collections.abc import Callable
from dataclasses import dataclass
from logging.handlers import MemoryHandler, RotatingFileHandler
from typing import TYPE_CHECKING, TextIO

from ... import __version__
from ...i18n import _, current_language
from ..appdirs import crash_path, data_dir, log_path
from .about import package_versions

if TYPE_CHECKING:  # not at run time: the config (pydantic, styles) is not loaded this early
    from ..config import LoadedConfig, LogConfig

log = logging.getLogger(__name__)

LOGGER = "qe_studio"
FORMAT = "%(asctime)s %(levelname)s [%(process)d %(threadName)s] %(name)s: %(message)s"
MAX_RECORD_CHARS = 16_000  # a record is never longer, traceback included (spec 89 R3.2)
_ROOM_FOR_THE_MARK = 40
_PENDING_CAPACITY = 1000  # no target to flush to: it only says when ``flush`` is tried, in vain
_BACKUPS = 1  # lain.log and lain.log.1: half of the limit each, so the limit is the total


class _CuttingFormatter(logging.Formatter):
    """Cuts the finished text in the middle: the start says what, the end says where it stopped.
    The record stays whole for the other handler, which formats it again."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if len(text) <= MAX_RECORD_CHARS:
            return text
        kept = MAX_RECORD_CHARS - _ROOM_FOR_THE_MARK
        head = kept // 2
        return f"{text[:head]}… [{len(text) - kept} characters cut] …{text[head - kept :]}"


@dataclass
class _Session:
    """What ``start`` and ``apply_config`` installed on the root logger."""

    verbose: bool
    terminal: logging.Handler
    pending: MemoryHandler | None  # until the first ``apply_config``
    thread_hook: Callable  # the ``threading.excepthook`` to put back
    file: RotatingFileHandler | None = None
    crash: TextIO | None = None  # ``lain.crash``, which ``faulthandler`` holds while it is open
    off: bool = False


_session: _Session | None = None


def start(verbose: bool = False) -> None:
    """Log to the terminal, and to memory until the config says where the file goes."""
    global _session
    stop()
    logging.raiseExceptions = False  # a failed write never prints nor reaches the program
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    logging.getLogger(LOGGER).setLevel(logging.DEBUG if verbose else logging.INFO)
    terminal = logging.StreamHandler()
    terminal.setLevel(logging.DEBUG if verbose else logging.WARNING)
    terminal.setFormatter(_CuttingFormatter(FORMAT))
    pending = MemoryHandler(
        _PENDING_CAPACITY, flushLevel=logging.CRITICAL + 1, target=None, flushOnClose=False
    )
    root.addHandler(terminal)
    root.addHandler(pending)
    _session = _Session(verbose, terminal, pending, threading.excepthook)
    logging.captureWarnings(True)
    threading.excepthook = _thread_failed


def apply_config(config: LogConfig) -> str | None:
    """Open, change or close the file as ``config`` asks; the warning to show comes back.

    The same settings leave the open file alone. The folder is the data folder in use, which only
    changes on a restart. Before ``start`` (a window a test built) there is nothing to apply to.
    """
    session = _session
    if session is None:
        return None
    warning = None
    if not config.enabled:
        _close_file(session)
    elif session.file is not None:
        session.file.maxBytes = _bytes_per_file(config)
    else:
        warning = _open_file(session, config)
    _release_pending(session)
    session.off = session.file is None
    logging.getLogger(LOGGER).setLevel(_package_level(session, config))
    _follow_the_file(session)
    return warning


def log_is_off() -> bool:
    """No log file in this session: off in the config, or it could not be opened. Not yet known (no
    ``apply_config`` so far) counts as on."""
    return _session is not None and _session.off


def stop() -> None:
    """Take out what ``start`` and ``apply_config`` installed."""
    global _session
    session = _session
    if session is None:
        return
    _close_crash_file(session)
    logging.captureWarnings(False)
    threading.excepthook = session.thread_hook
    root = logging.getLogger()
    for handler in (session.terminal, session.pending, session.file):
        if handler is not None:
            root.removeHandler(handler)
            handler.close()
    _session = None


def session_lines(loaded: LoadedConfig, settings_file: str) -> list[str]:
    """What a bug report needs to know about this session (spec 90 R2). Host, user and paths are
    there because they explain a sync; no password, ``password_env`` or e-mail ever is."""
    config = loaded.config
    cluster = config.cluster
    where = (
        f"{cluster.user}@{cluster.host}:{cluster.port} auth={cluster.auth} "
        f"multiplex={cluster.multiplex}"
        if cluster.configured
        else "not configured"
    )
    return [
        f"session: Lain {__version__} pid={os.getpid()} platform={platform.platform()} "
        f"language={current_language()}",
        f"session: config={loaded.path or 'none'} data={data_dir()} settings={settings_file}",
        f"session: local_root={config.paths.local_root} remote_root={config.paths.remote_root}",
        f"session: cluster={where}",
        f"session: log={log_path()} level={config.log.level} limit={config.log.max_size_mb} MB",
    ]


def log_versions() -> None:
    """The versions of the stack, from the installed metadata: run it in a worker (R2.2)."""
    versions = " ".join(f"{name.lower()}={version}" for name, version in package_versions())
    log.info("session: %s", versions)


def _thread_failed(args: threading.ExceptHookArgs) -> None:
    """``threading.excepthook``: a ``threading.Thread`` that died only printed to stderr."""
    if args.exc_type is SystemExit:  # what the default hook ignores too
        return
    name = args.thread.name if args.thread is not None else "?"
    log.error("thread %s failed", name, exc_info=args.exc_value)


def _follow_the_file(session: _Session) -> None:
    """``lain.crash`` lives as long as the log file does: no log, no second file."""
    if session.file is None:
        _close_crash_file(session)
    elif session.crash is None:
        _open_crash_file(session)


def _open_crash_file(session: _Session) -> None:
    """Log the crash the last session left, then send the next one to the same file: a fixed
    descriptor, which the rotation of ``lain.log`` would move. ``faulthandler`` already on (``python
    -X faulthandler``, pytest) is someone else's choice: it stays where they sent it."""
    path = crash_path()
    try:
        if path.is_file() and (text := path.read_text(encoding="utf-8", errors="replace").strip()):
            log.error("session: the previous session crashed:\n%s", text)
            os.truncate(path, 0)
        if faulthandler.is_enabled():
            return
        crash = path.open("a", encoding="utf-8")
    except OSError as exc:
        log.warning("session: no crash file (%s): %s", path, exc)
        return
    faulthandler.enable(file=crash, all_threads=True)
    session.crash = crash


def _close_crash_file(session: _Session) -> None:
    if session.crash is not None:
        faulthandler.disable()
        session.crash.close()
        session.crash = None


def _bytes_per_file(config: LogConfig) -> int:
    return config.max_size_mb * 1_000_000 // (_BACKUPS + 1)


def _open_file(session: _Session, config: LogConfig) -> str | None:
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=_bytes_per_file(config),
            backupCount=_BACKUPS,
            encoding="utf-8",
            errors="backslashreplace",  # names read from rsync with surrogateescape (spec 89 R3)
        )
    except OSError as exc:
        text = _(
            "Não foi possível gravar o log em {path} ({error}); esta sessão não tem arquivo de log."
        )
        return text.format(path=path, error=exc.strerror or exc)
    handler.setFormatter(_CuttingFormatter(FORMAT))
    logging.getLogger().addHandler(handler)
    session.file = handler
    return None


def _close_file(session: _Session) -> None:
    if session.file is not None:
        logging.getLogger().removeHandler(session.file)
        session.file.close()
        session.file = None


def _release_pending(session: _Session) -> None:
    """What was logged before the first config goes to the file, or nowhere when there is none."""
    pending, session.pending = session.pending, None
    if pending is None:
        return
    logging.getLogger().removeHandler(pending)
    if session.file is not None:
        pending.setTarget(session.file)
        pending.flush()
    pending.close()


def _package_level(session: _Session, config: LogConfig) -> int:
    if session.verbose:
        return logging.DEBUG
    if session.file is None:
        return logging.WARNING  # only the terminal listens, and it starts at WARNING
    return logging.DEBUG if config.level == "debug" else logging.INFO
