"""Application bootstrap: arguments, logging, config, theme and main window."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QLockFile, QSettings, QThreadPool
from PyQt6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME, __version__
from ..core.app import logs
from ..core.appdirs import lock_path, set_data_dir, settings_file
from ..core.config import ConfigError, load_config
from ..core.plotting.style import register_fonts
from ..core.tasks import run_task
from ..i18n import _
from .shell.app_identity import configure_application
from .shell.excepthook import install_excepthook, set_excepthook_window
from .shell.language_install import install_qt_translator
from .shell.qt_log import install_qt_log
from .shutdown import ShutdownReport
from .theme.manager import MODES, ThemeManager

log = logging.getLogger(__name__)

# Workers still running after the window closed get this long; then ``finish`` leaves.
POOL_WAIT_MS = 2000


def acquire_instance_lock(path: Path) -> QLockFile | None:
    """Lock ``path`` for this running app (spec 27-3 R4.3). ``None``: another instance holds it.

    The stores (in the root's settings folder since spec 48) are written whole by whoever saves last,
    so two instances would lose each other's changes; this lets the second one say so (it only warns:
    see ``main``). The lock is the user's, not the root's: another user or machine sharing the root
    is not seen (spec 48, accepted). A lock left
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
        log.warning("no folder for the instance lock (%s): %s", path.parent, exc)
        return lock
    if lock.tryLock(0):
        return lock
    if lock.error() == QLockFile.LockError.LockFailedError:
        return None
    log.warning("instance lock unavailable (%s): error %s", path, lock.error().name)
    return lock


def ask_open_anyway() -> bool:
    """The question of a second instance; Não (the default) leaves."""
    answer = QMessageBox.question(
        None,
        APP_NAME,
        _("O Lain já está aberto com esta configuração. Abrir mesmo assim?"),
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
    started: float | None = None,
) -> int:
    """After ``app.exec()``: no worker may outlive the interpreter (spec 27-5 R1.3).

    The global pool gets ``POOL_WAIT_MS`` more. If a task is still running then, the interpreter
    must not finalize with Qt threads inside Python (a crash, or a wait without end): the state was
    written by ``closeEvent`` already, so say what was late and leave at once (``exit_now``).
    ``started``: the ``time.monotonic()`` of ``main``, for the last line of the session.
    """
    log.info(
        "session: end code=%d after %d s",
        code,
        0 if started is None else time.monotonic() - started,
    )
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


def open_settings(path: Path | None, legacy: QSettings | None = None) -> QSettings:
    """The QSettings of the session: the system's, or the ``settings.ini`` of ``paths.data``.

    A ``settings.ini`` with no key yet gets a copy of ``legacy`` (the system's QSettings) once, so
    the interface comes back as it was; the old file is left as it is (spec 61 R2.5).
    """
    if path is None:
        return QSettings()
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    if settings.allKeys():
        return settings
    source = legacy if legacy is not None else QSettings()
    keys = source.allKeys()
    for key in keys:
        settings.setValue(key, source.value(key))
    if keys:
        settings.sync()
        logging.getLogger("qe_studio").info(
            "interface settings copied from %s to %s (%d keys)", source.fileName(), path, len(keys)
        )
    return settings


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lain", description=APP_NAME)
    parser.add_argument("--config", help=_("caminho do config.yaml"))
    parser.add_argument("--verbose", action="store_true", help=_("log detalhado"))
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    logs.start(args.verbose)
    install_qt_log()
    install_excepthook()
    app = QApplication(sys.argv[:1])
    configure_application(app)
    install_qt_translator(app)
    register_fonts()

    try:
        loaded = load_config(args.config)
    except ConfigError as exc:
        ThemeManager("dark").apply(app)
        QMessageBox.critical(None, _("config.yaml inválido"), str(exc))
        return 2
    # The data folder comes from the config, and the QSettings may live in it (spec 61 R2.4).
    if warning := set_data_dir(loaded.config.paths.data):
        loaded.warnings.insert(0, warning)
    # The log file lives in that folder too (spec 89 R2).
    if warning := logs.apply_config(loaded.config.log):
        loaded.warnings.insert(0, warning)
    settings = open_settings(settings_file())
    for line in logs.session_lines(loaded, settings.fileName()):
        log.info("%s", line)
    log.info("session: qt=%s pyqt=%s", QT_VERSION_STR, PYQT_VERSION_STR)

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
    run_task(logs.log_versions)  # in a worker: the GUI does not read the packages' metadata
    code = app.exec()
    pool = QThreadPool.globalInstance()
    return finish(code, pool, lock, window.shutdown_report, started=started)
