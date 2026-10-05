"""Application bootstrap: arguments, logging, config, theme and main window."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QLockFile, QSettings, QThreadPool
from PyQt6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME, __version__
from ..core.appdirs import lock_path, log_path
from ..core.config import ConfigError, load_config
from ..core.plotting.style import register_fonts
from .app_identity import configure_application
from .excepthook import install_excepthook, set_excepthook_window
from .shutdown import ShutdownReport
from .theme.manager import MODES, ThemeManager

# Workers still running after the window closed get this long; then ``finish`` leaves.
POOL_WAIT_MS = 2000


def setup_logging(verbose: bool = False) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def acquire_instance_lock(path: Path) -> QLockFile | None:
    """Lock ``path`` for this running app (spec 27-3 R4.3). ``None``: another instance holds it.

    The stores in the data dir are written whole by whoever saves last, so two instances would lose
    each other's changes; this lets the second one say so (it only warns: see ``main``). A lock left
    by a process that is gone is taken over by ``QLockFile`` itself. Its age must not count
    (``setStaleLockTime(0)``): by default a lock held for 30 s is "stale" even though its owner is
    alive, and a second instance started later would steal it.

    When the lock cannot be made at all (a read-only data dir) the unlocked object comes back and
    the app goes on: that is not a reason to bother the user.
    """
    log = logging.getLogger("qe_studio")
    lock = QLockFile(str(path))
    lock.setStaleLockTime(0)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("sem pasta para a trava de instância (%s): %s", path.parent, exc)
        return lock
    if lock.tryLock(0):
        return lock
    if lock.error() == QLockFile.LockError.LockFailedError:
        return None
    log.warning("trava de instância indisponível (%s): erro %s", path, lock.error().name)
    return lock


def ask_open_anyway() -> bool:
    """The question of a second instance; Não (the default) leaves."""
    answer = QMessageBox.question(
        None,
        APP_NAME,
        "O Lain já está aberto com esta configuração. Abrir mesmo assim?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def claim_instance(path: Path) -> tuple[bool, QLockFile | None]:
    """(go on?, the lock to keep until exit). A second instance asks first: yes goes on without a
    lock (and says so in the log: the user may want two windows on different projects), no leaves."""
    lock = acquire_instance_lock(path)
    if lock is not None:
        return True, lock
    if not ask_open_anyway():
        return False, None
    logging.getLogger("qe_studio").warning(
        "segunda instância aberta sem trava (escolha do usuário)"
    )
    return True, None


def finish(
    code: int,
    pool: QThreadPool | None,
    lock: QLockFile | None,
    report: ShutdownReport | None,
    exit_now: Callable[[int], object] = os._exit,
) -> int:
    """After ``app.exec()``: no worker may outlive the interpreter (spec 27-5 R1.3).

    The global pool gets ``POOL_WAIT_MS`` more. If a task is still running then, the interpreter
    must not finalize with Qt threads inside Python (a crash, or a wait without end): the state was
    written by ``closeEvent`` already, so say what was late and leave at once (``exit_now``).
    """
    drained = pool is None or pool.waitForDone(POOL_WAIT_MS)
    if lock is not None:
        lock.unlock()
    if drained:
        return code
    late = report.late if report is not None else []
    logging.getLogger("qe_studio").error(
        "encerramento: %d tarefa(s) ainda rodando após %d ms (passos atrasados: %s); saindo",
        pool.activeThreadCount() if pool is not None else 0,
        POOL_WAIT_MS,
        late or "nenhum",
    )
    logging.shutdown()
    exit_now(code)
    return code  # only reached when ``exit_now`` is replaced (tests)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lain", description=APP_NAME)
    parser.add_argument("--config", help="caminho do config.yaml")
    parser.add_argument("--verbose", action="store_true", help="log detalhado")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    install_excepthook()
    app = QApplication(sys.argv[:1])
    configure_application(app)
    register_fonts()

    settings = QSettings()
    try:
        loaded = load_config(args.config)
    except ConfigError as exc:
        ThemeManager("dark").apply(app)
        QMessageBox.critical(None, "config.yaml inválido", str(exc))
        return 2

    mode = str(settings.value("ui/theme", loaded.config.ui.theme))
    theme = ThemeManager(
        mode if mode in MODES else loaded.config.ui.theme, font_scale=loaded.config.ui.font_scale
    )
    theme.apply(app)

    # After the theme (the question is styled) and the config (an invalid one is reported first);
    # the lock is held until ``main`` returns.
    proceed, lock = claim_instance(lock_path())
    if not proceed:
        return 0

    from .main_window import MainWindow

    window = MainWindow(loaded, theme, settings)
    set_excepthook_window(window)  # from here on an unexpected error is a toast, not a box
    window.show()
    code = app.exec()
    return finish(code, QThreadPool.globalInstance(), lock, window.shutdown_report)
